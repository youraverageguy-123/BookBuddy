use serde::{Deserialize, Serialize};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::utils::config::Color;
use tauri::{AppHandle, Emitter, Manager, State, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_window_state::StateFlags;

const TOTAL_PROGRESS_STAGES: u8 = 6;
const BACKEND_SLOW_AFTER: Duration = Duration::from_secs(30);
const FRONTEND_SLOW_AFTER: Duration = Duration::from_secs(30);
const FRONTEND_FAIL_AFTER: Duration = Duration::from_secs(60);
const LOG_ROTATE_BYTES: u64 = 5 * 1024 * 1024;

#[derive(Clone, Debug)]
struct DataLayout {
    library: PathBuf,
    database: PathBuf,
    logs: PathBuf,
    cache: PathBuf,
    config: PathBuf,
    exports: PathBuf,
    runtime: PathBuf,
}

const EMBEDDED_BACKEND: &[u8] =
    include_bytes!("../binaries/bookbuddy-backend-x86_64-pc-windows-msvc.exe");

fn directory_fingerprint(root: &Path) -> Result<(u64, u64), std::io::Error> {
    if !root.exists() {
        return Ok((0, 0));
    }
    let mut files = 0;
    let mut bytes = 0;
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        if kind.is_symlink() {
            return Err(std::io::Error::other(
                "library migration does not follow symlinks",
            ));
        }
        if kind.is_dir() {
            let nested = directory_fingerprint(&entry.path())?;
            files += nested.0;
            bytes += nested.1;
        } else if kind.is_file() {
            files += 1;
            bytes += entry.metadata()?.len();
        }
    }
    Ok((files, bytes))
}

fn copy_directory(source: &Path, target: &Path) -> Result<(), std::io::Error> {
    fs::create_dir_all(target)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        let destination = target.join(entry.file_name());
        if kind.is_symlink() {
            return Err(std::io::Error::other(
                "library migration does not follow symlinks",
            ));
        }
        if kind.is_dir() {
            copy_directory(&entry.path(), &destination)?;
        } else if kind.is_file() {
            fs::copy(entry.path(), destination)?;
        }
    }
    Ok(())
}

fn migrate_legacy_library(legacy: &Path, library: &Path) -> Result<(), std::io::Error> {
    if !legacy.is_dir() || library.exists() {
        return Ok(());
    }
    let parent = library
        .parent()
        .ok_or_else(|| std::io::Error::other("invalid library path"))?;
    fs::create_dir_all(parent)?;
    let staging = parent.join(format!(".library-migration-{}", uuid::Uuid::new_v4()));
    copy_directory(legacy, &staging)?;
    if directory_fingerprint(legacy)? != directory_fingerprint(&staging)? {
        let _ = fs::remove_dir_all(&staging);
        return Err(std::io::Error::other(
            "library migration verification failed",
        ));
    }
    fs::rename(staging, library)?;
    Ok(())
}

fn create_data_layout(
    root: PathBuf,
    legacy_library: Option<&Path>,
) -> Result<DataLayout, std::io::Error> {
    let layout = DataLayout {
        library: root.join("library"),
        database: root.join("database"),
        logs: root.join("logs"),
        cache: root.join("cache"),
        config: root.join("config"),
        exports: root.join("exports"),
        runtime: root.join("runtime"),
    };
    if let Some(legacy) = legacy_library {
        migrate_legacy_library(legacy, &layout.library)?;
    }
    for path in [
        &layout.library,
        &layout.database,
        &layout.logs,
        &layout.cache,
        &layout.config,
        &layout.exports,
        &layout.runtime,
    ] {
        fs::create_dir_all(path)?;
    }
    Ok(layout)
}

#[cfg_attr(debug_assertions, allow(dead_code))]
fn is_bookbuddy_directory(path: &Path) -> bool {
    path.file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.eq_ignore_ascii_case("BookBuddy"))
}

#[cfg(debug_assertions)]
fn source_project_root() -> Option<PathBuf> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
}

fn portable_data_root() -> Result<PathBuf, std::io::Error> {
    #[cfg(debug_assertions)]
    {
        return source_project_root()
            .ok_or_else(|| std::io::Error::other("project root unavailable"));
    }
    #[cfg(not(debug_assertions))]
    {
        let executable = std::env::current_exe()?;
        let parent = executable
            .parent()
            .ok_or_else(|| std::io::Error::other("executable directory unavailable"))?;
        if is_bookbuddy_directory(parent) {
            Ok(parent.to_path_buf())
        } else {
            Ok(parent.join("BookBuddy"))
        }
    }
}

fn legacy_library_path(portable_root: &Path) -> Option<PathBuf> {
    #[cfg(target_os = "windows")]
    let legacy = [
        std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .map(|path| path.join("BookBuddy").join("library")),
        std::env::var_os("APPDATA")
            .map(PathBuf::from)
            .map(|path| path.join("com.bookbuddy.reader").join("library")),
    ]
    .into_iter()
    .flatten()
    .find(|path| path.is_dir() && path != &portable_root.join("library"));
    #[cfg(not(target_os = "windows"))]
    let legacy = None;
    legacy.filter(|path| path != &portable_root.join("library"))
}

fn migrate_legacy_config(config: &Path) -> Result<(), std::io::Error> {
    #[cfg(target_os = "windows")]
    if let Some(legacy) = std::env::var_os("APPDATA")
        .map(PathBuf::from)
        .map(|path| path.join("com.bookbuddy.reader"))
    {
        for name in [
            "reader_settings.json",
            "reader-state.json",
            ".window-state.json",
        ] {
            let source = legacy.join(name);
            let target = config.join(name);
            if source.is_file() && !target.exists() {
                fs::copy(source, target)?;
            }
        }
    }
    Ok(())
}

fn prepare_data_layout() -> Result<DataLayout, std::io::Error> {
    let root = portable_data_root()?;
    let legacy = legacy_library_path(&root);
    let layout = create_data_layout(root, legacy.as_deref())?;
    migrate_legacy_config(&layout.config)?;
    Ok(layout)
}

fn materialize_embedded_backend(layout: &DataLayout) -> Result<PathBuf, std::io::Error> {
    let target = layout.runtime.join(format!(
        "bookbuddy-backend-{}.exe",
        env!("BOOKBUDDY_BACKEND_FINGERPRINT")
    ));
    if target
        .metadata()
        .map(|metadata| metadata.len() == EMBEDDED_BACKEND.len() as u64)
        .unwrap_or(false)
    {
        return Ok(target);
    }
    let temporary = layout
        .runtime
        .join(format!(".bookbuddy-backend-{}.tmp", uuid::Uuid::new_v4()));
    fs::write(&temporary, EMBEDDED_BACKEND)?;
    fs::rename(&temporary, &target)?;
    Ok(target)
}

#[cfg(all(target_os = "windows", not(debug_assertions)))]
fn copy_release_installers(source_dir: &Path, target_dir: &Path) -> Result<(), std::io::Error> {
    for entry in fs::read_dir(source_dir)? {
        let entry = entry?;
        if !entry.file_type()?.is_file() {
            continue;
        }
        let name = entry.file_name();
        let Some(name_text) = name.to_str() else {
            continue;
        };
        if name_text.starts_with("BookBuddy_") && name_text.ends_with("_x64-setup.exe") {
            fs::copy(entry.path(), target_dir.join(name))?;
        }
    }
    Ok(())
}

#[cfg(all(target_os = "windows", not(debug_assertions)))]
fn relocate_portable_executable() -> Result<bool, std::io::Error> {
    let current = std::env::current_exe()?;
    let source_dir = current
        .parent()
        .ok_or_else(|| std::io::Error::other("executable directory unavailable"))?;
    if is_bookbuddy_directory(source_dir) {
        return Ok(false);
    }
    let target_dir = source_dir.join("BookBuddy");
    fs::create_dir_all(&target_dir)?;
    copy_release_installers(source_dir, &target_dir)?;
    let target = target_dir.join("BookBuddy.exe");
    let temporary = target_dir.join(format!(".BookBuddy-{}.tmp", uuid::Uuid::new_v4()));
    fs::copy(&current, &temporary)?;
    if target.exists() {
        fs::remove_file(&target)?;
    }
    fs::rename(&temporary, &target)?;
    let mut command = Command::new(&target);
    command
        .args(std::env::args_os().skip(1))
        .current_dir(&target_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    hide_console(&mut command);
    command.spawn()?;
    Ok(true)
}

#[cfg(not(all(target_os = "windows", not(debug_assertions))))]
fn relocate_portable_executable() -> Result<bool, std::io::Error> {
    Ok(false)
}

#[cfg(target_os = "windows")]
fn hide_console(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x08000000;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(target_os = "windows"))]
fn hide_console(_command: &mut Command) {}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct BackendConnection {
    base_url: String,
    token: Option<String>,
    managed: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
enum StartupStage {
    Launching,
    StartingBackend,
    ConnectingBackend,
    BackendHealthy,
    LoadingConfiguration,
    InitializingReact,
    RestoringSession,
    LoadingLibrary,
    Ready,
    Transition,
    Complete,
    Failed,
}

impl StartupStage {
    fn rank(self) -> u8 {
        match self {
            Self::Launching => 0,
            Self::StartingBackend => 1,
            Self::ConnectingBackend => 2,
            Self::BackendHealthy => 3,
            Self::LoadingConfiguration => 4,
            Self::InitializingReact => 5,
            Self::RestoringSession => 6,
            Self::LoadingLibrary => 7,
            Self::Ready => 8,
            Self::Transition => 9,
            Self::Complete => 10,
            Self::Failed => 255,
        }
    }

    fn completed_stages(self) -> u8 {
        match self {
            Self::Launching | Self::StartingBackend => 0,
            Self::ConnectingBackend => 1,
            Self::BackendHealthy | Self::LoadingConfiguration | Self::InitializingReact => 2,
            Self::RestoringSession => 3,
            Self::LoadingLibrary => 4,
            Self::Ready | Self::Transition | Self::Complete => 6,
            Self::Failed => 0,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct StartupEvent {
    attempt: u64,
    stage: StartupStage,
    message: String,
    completed_stages: u8,
    total_stages: u8,
    kind: &'static str,
    actions: Vec<&'static str>,
}

#[derive(Deserialize)]
struct HealthStorage {
    library: String,
}

#[derive(Deserialize)]
struct HealthPayload {
    schema_version: String,
    status: String,
    storage: HealthStorage,
}

#[derive(Serialize)]
struct TimingRecord<'a> {
    run_id: &'a str,
    attempt: u64,
    timestamp_ms: u128,
    elapsed_ms: u128,
    stage: StartupStage,
    outcome: &'a str,
    error_code: Option<&'a str>,
}

struct StartupRuntime {
    connection: Mutex<Option<BackendConnection>>,
    child: Mutex<Option<Child>>,
    stage: Mutex<StartupStage>,
    attempt: AtomicU64,
    backend_healthy: AtomicBool,
    transition_started: AtomicBool,
    handoff_complete: AtomicBool,
    started: Instant,
    run_id: String,
    log_path: PathBuf,
}

impl StartupRuntime {
    fn new(log_path: PathBuf, started: Instant) -> Self {
        Self {
            connection: Mutex::new(None),
            child: Mutex::new(None),
            stage: Mutex::new(StartupStage::Launching),
            attempt: AtomicU64::new(0),
            backend_healthy: AtomicBool::new(false),
            transition_started: AtomicBool::new(false),
            handoff_complete: AtomicBool::new(false),
            started,
            run_id: uuid::Uuid::new_v4().to_string(),
            log_path,
        }
    }

    fn current_attempt(&self) -> u64 {
        self.attempt.load(Ordering::SeqCst)
    }

    fn current_stage(&self) -> StartupStage {
        self.stage
            .lock()
            .map(|value| *value)
            .unwrap_or(StartupStage::Failed)
    }

    fn is_current(&self, attempt: u64) -> bool {
        self.current_attempt() == attempt
    }

    fn log(&self, attempt: u64, stage: StartupStage, outcome: &str, error_code: Option<&str>) {
        if let Some(parent) = self.log_path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        rotate_log(&self.log_path);
        let record = TimingRecord {
            run_id: &self.run_id,
            attempt,
            timestamp_ms: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis(),
            elapsed_ms: self.started.elapsed().as_millis(),
            stage,
            outcome,
            error_code,
        };
        if let Ok(line) = serde_json::to_string(&record) {
            if let Ok(mut file) = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&self.log_path)
            {
                let _ = writeln!(file, "{line}");
            }
        }
    }
}

fn rotate_log(path: &Path) {
    if path.metadata().map(|value| value.len()).unwrap_or(0) < LOG_ROTATE_BYTES {
        return;
    }
    let backup = path.with_extension("jsonl.1");
    let _ = fs::remove_file(&backup);
    let _ = fs::rename(path, backup);
}

fn event_for(
    attempt: u64,
    stage: StartupStage,
    message: impl Into<String>,
    kind: &'static str,
    actions: Vec<&'static str>,
) -> StartupEvent {
    StartupEvent {
        attempt,
        stage,
        message: message.into(),
        completed_stages: stage.completed_stages(),
        total_stages: TOTAL_PROGRESS_STAGES,
        kind,
        actions,
    }
}

fn emit_event(app: &AppHandle, runtime: &StartupRuntime, event: StartupEvent) {
    if event.attempt != runtime.current_attempt() {
        return;
    }
    if event.kind != "slow" {
        if let Ok(mut stage) = runtime.stage.lock() {
            *stage = event.stage;
        }
    }
    runtime.log(event.attempt, event.stage, event.kind, None);
    let _ = app.emit_to("splash", "bookbuddy://startup-stage", event);
}

fn fail_startup(
    app: &AppHandle,
    runtime: &StartupRuntime,
    attempt: u64,
    message: &str,
    code: &'static str,
) {
    if !runtime.is_current(attempt) {
        return;
    }
    if let Ok(mut stage) = runtime.stage.lock() {
        *stage = StartupStage::Failed;
    }
    runtime.log(attempt, StartupStage::Failed, "failure", Some(code));
    let _ = app.emit_to(
        "splash",
        "bookbuddy://startup-stage",
        event_for(
            attempt,
            StartupStage::Failed,
            message,
            "failure",
            vec!["retry", "exit"],
        ),
    );
}

fn stop_backend(runtime: &StartupRuntime) {
    if let Ok(mut child) = runtime.child.lock() {
        if let Some(process) = child.as_mut() {
            #[cfg(target_os = "windows")]
            {
                let mut command = Command::new("taskkill");
                command
                    .args(["/PID", &process.id().to_string(), "/T", "/F"])
                    .stdin(Stdio::null())
                    .stdout(Stdio::null())
                    .stderr(Stdio::null());
                hide_console(&mut command);
                let _ = command.status();
            }
            let _ = process.kill();
            let _ = process.wait();
        }
        *child = None;
    }
    runtime.backend_healthy.store(false, Ordering::SeqCst);
    if let Ok(mut connection) = runtime.connection.lock() {
        *connection = None;
    }
}

fn free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|error| error.to_string())?;
    Ok(listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port())
}

fn spawn_backend(_app: &AppHandle) -> Result<(BackendConnection, Child), &'static str> {
    let port = free_port().map_err(|_| "backend_port_unavailable")?;
    let token = uuid::Uuid::new_v4().to_string();
    let layout = prepare_data_layout().map_err(|_| "app_directory_create_failed")?;
    let executable = materialize_embedded_backend(&layout).map_err(|_| "backend_extract_failed")?;
    let mut command = Command::new(executable);
    command
        .env("BOOKBUDDY_HOST", "127.0.0.1")
        .env("BOOKBUDDY_PORT", port.to_string())
        .env("BOOKBUDDY_API_TOKEN", &token)
        .env("BOOKBUDDY_LIBRARY_DIR", &layout.library)
        .env("BOOKBUDDY_CACHE_DIR", &layout.cache)
        .env("BOOKBUDDY_LOG_DIR", &layout.logs)
        .env("BOOKBUDDY_CONFIG_DIR", &layout.config)
        .env(
            "BOOKBUDDY_PROJECT_ROOT",
            portable_data_root().map_err(|_| "app_data_unavailable")?,
        )
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    hide_console(&mut command);
    let child = command.spawn().map_err(|_| "backend_spawn_failed")?;
    Ok((
        BackendConnection {
            base_url: format!("http://127.0.0.1:{port}"),
            token: Some(token),
            managed: true,
        },
        child,
    ))
}

fn validate_health(payload: &HealthPayload) -> Result<(), &'static str> {
    if payload.schema_version != "bookbuddy_health_v1" || payload.status != "ready" {
        return Err("backend_health_contract_invalid");
    }
    if payload.storage.library != "available" {
        return Err("backend_library_unavailable");
    }
    Ok(())
}

fn create_main_window(app: &AppHandle) -> Result<(), &'static str> {
    if let Some(existing) = app.get_webview_window("main") {
        let _ = existing.close();
    }
    WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
        .title("BookBuddy")
        .inner_size(1280.0, 820.0)
        .min_inner_size(760.0, 560.0)
        .center()
        .visible(false)
        .background_color(Color(23, 24, 22, 255))
        .build()
        .map(|_| ())
        .map_err(|_| "main_window_create_failed")
}

fn start_frontend_watchdog(app: AppHandle, runtime: Arc<StartupRuntime>, attempt: u64) {
    thread::spawn(move || {
        thread::sleep(FRONTEND_SLOW_AFTER);
        if runtime.is_current(attempt)
            && runtime.current_stage().rank() < StartupStage::Ready.rank()
        {
            emit_event(
                &app,
                &runtime,
                event_for(
                    attempt,
                    runtime.current_stage(),
                    "Preparing interface...",
                    "slow",
                    vec![],
                ),
            );
        }
        thread::sleep(FRONTEND_FAIL_AFTER - FRONTEND_SLOW_AFTER);
        if runtime.is_current(attempt)
            && runtime.current_stage().rank() < StartupStage::Ready.rank()
        {
            fail_startup(
                &app,
                &runtime,
                attempt,
                "Preparing interface...",
                "frontend_timeout",
            );
        }
    });
}

fn begin_frontend(app: &AppHandle, runtime: Arc<StartupRuntime>, attempt: u64) {
    emit_event(
        app,
        &runtime,
        event_for(
            attempt,
            StartupStage::LoadingConfiguration,
            "Preparing interface...",
            "progress",
            vec![],
        ),
    );
    match create_main_window(app) {
        Ok(()) => {
            runtime.log(
                attempt,
                StartupStage::LoadingConfiguration,
                "main_window_created",
                None,
            );
            start_frontend_watchdog(app.clone(), runtime, attempt);
        }
        Err(code) => fail_startup(
            app,
            &runtime,
            attempt,
            "Unable to prepare BookBuddy interface.",
            code,
        ),
    }
}

fn run_backend_attempt(app: AppHandle, runtime: Arc<StartupRuntime>, attempt: u64) {
    emit_event(
        &app,
        &runtime,
        event_for(
            attempt,
            StartupStage::StartingBackend,
            "Starting reading engine...",
            "progress",
            vec![],
        ),
    );
    let (connection, child) = match spawn_backend(&app) {
        Ok(value) => value,
        Err(code) => {
            fail_startup(
                &app,
                &runtime,
                attempt,
                "Unable to start BookBuddy engine.",
                code,
            );
            return;
        }
    };
    if !runtime.is_current(attempt) {
        let mut child = child;
        let _ = child.kill();
        return;
    }
    if let Ok(mut slot) = runtime.child.lock() {
        *slot = Some(child);
    }
    if let Ok(mut slot) = runtime.connection.lock() {
        *slot = Some(connection.clone());
    }
    runtime.log(
        attempt,
        StartupStage::StartingBackend,
        "backend_spawned",
        None,
    );
    emit_event(
        &app,
        &runtime,
        event_for(
            attempt,
            StartupStage::ConnectingBackend,
            "Connecting to backend...",
            "progress",
            vec![],
        ),
    );

    let client = match reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
    {
        Ok(client) => client,
        Err(_) => {
            fail_startup(
                &app,
                &runtime,
                attempt,
                "Unable to start BookBuddy engine.",
                "health_client_failed",
            );
            return;
        }
    };
    let polling_started = Instant::now();
    let mut slow_emitted = false;
    loop {
        if !runtime.is_current(attempt) {
            return;
        }
        let exited = runtime
            .child
            .lock()
            .ok()
            .and_then(|mut value| {
                value
                    .as_mut()
                    .and_then(|child| child.try_wait().ok().flatten())
            })
            .is_some();
        if exited {
            fail_startup(
                &app,
                &runtime,
                attempt,
                "Unable to start BookBuddy engine.",
                "backend_exited",
            );
            return;
        }
        let mut request = client.get(format!("{}/health", connection.base_url));
        if let Some(token) = &connection.token {
            request = request.bearer_auth(token);
        }
        match request.send() {
            Ok(response) if response.status().is_success() => {
                match response.json::<HealthPayload>() {
                    Ok(payload) => match validate_health(&payload) {
                        Ok(()) => break,
                        Err(code) => {
                            fail_startup(
                                &app,
                                &runtime,
                                attempt,
                                "Unable to start BookBuddy engine.",
                                code,
                            );
                            return;
                        }
                    },
                    Err(_) => {
                        fail_startup(
                            &app,
                            &runtime,
                            attempt,
                            "Unable to start BookBuddy engine.",
                            "backend_health_contract_invalid",
                        );
                        return;
                    }
                }
            }
            Ok(response) if response.status().is_client_error() => {
                fail_startup(
                    &app,
                    &runtime,
                    attempt,
                    "Unable to start BookBuddy engine.",
                    "backend_health_rejected",
                );
                return;
            }
            _ => {}
        }
        if !slow_emitted && polling_started.elapsed() >= BACKEND_SLOW_AFTER {
            slow_emitted = true;
            emit_event(
                &app,
                &runtime,
                event_for(
                    attempt,
                    StartupStage::ConnectingBackend,
                    "Backend is taking longer than expected...",
                    "slow",
                    vec![],
                ),
            );
        }
        thread::sleep(if slow_emitted {
            Duration::from_millis(500)
        } else {
            Duration::from_millis(100)
        });
    }

    runtime.backend_healthy.store(true, Ordering::SeqCst);
    emit_event(
        &app,
        &runtime,
        event_for(
            attempt,
            StartupStage::BackendHealthy,
            "Preparing interface...",
            "progress",
            vec![],
        ),
    );
    begin_frontend(&app, runtime, attempt);
}

fn start_full_attempt(app: AppHandle, runtime: Arc<StartupRuntime>) {
    let attempt = runtime.attempt.fetch_add(1, Ordering::SeqCst) + 1;
    runtime.transition_started.store(false, Ordering::SeqCst);
    runtime.handoff_complete.store(false, Ordering::SeqCst);
    stop_backend(&runtime);
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.close();
    }
    thread::spawn(move || run_backend_attempt(app, runtime, attempt));
}

fn start_frontend_retry(app: AppHandle, runtime: Arc<StartupRuntime>) {
    let attempt = runtime.attempt.fetch_add(1, Ordering::SeqCst) + 1;
    runtime.transition_started.store(false, Ordering::SeqCst);
    runtime.handoff_complete.store(false, Ordering::SeqCst);
    emit_event(
        &app,
        &runtime,
        event_for(
            attempt,
            StartupStage::BackendHealthy,
            "Preparing interface...",
            "progress",
            vec![],
        ),
    );
    thread::spawn(move || begin_frontend(&app, runtime, attempt));
}

fn complete_handoff(app: &AppHandle, runtime: &StartupRuntime, attempt: u64) {
    if !runtime.is_current(attempt) || runtime.handoff_complete.swap(true, Ordering::SeqCst) {
        return;
    }
    if let Some(splash) = app.get_webview_window("splash") {
        let _ = splash.close();
    }
    runtime.log(attempt, StartupStage::Transition, "splash_closed", None);
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.emit("bookbuddy://reveal-main", ());
        let _ = main.set_focus();
    }
    if let Ok(mut stage) = runtime.stage.lock() {
        *stage = StartupStage::Complete;
    }
    runtime.log(attempt, StartupStage::Complete, "complete", None);
}

#[tauri::command]
fn backend_connection(
    runtime: State<'_, Arc<StartupRuntime>>,
) -> Result<BackendConnection, String> {
    if !runtime.backend_healthy.load(Ordering::SeqCst) {
        return Err("backend_not_ready".into());
    }
    runtime
        .connection
        .lock()
        .map_err(|_| "backend_state_unavailable".to_string())?
        .clone()
        .ok_or_else(|| "backend_not_ready".into())
}

#[tauri::command]
fn startup_splash_ready(app: AppHandle, runtime: State<'_, Arc<StartupRuntime>>) {
    let attempt = runtime.current_attempt();
    runtime.log(attempt, StartupStage::Launching, "splash_first_paint", None);
    let stage = runtime.current_stage();
    let message = match stage {
        StartupStage::StartingBackend => "Starting reading engine...",
        StartupStage::ConnectingBackend => "Connecting to backend...",
        StartupStage::BackendHealthy
        | StartupStage::LoadingConfiguration
        | StartupStage::InitializingReact => "Preparing interface...",
        StartupStage::RestoringSession => "Restoring workspace...",
        StartupStage::LoadingLibrary => "Loading library...",
        StartupStage::Ready | StartupStage::Transition | StartupStage::Complete => "Ready",
        StartupStage::Failed => "Unable to start BookBuddy engine.",
        StartupStage::Launching => "Starting reading engine...",
    };
    let kind = if stage == StartupStage::Failed {
        "failure"
    } else {
        "progress"
    };
    let actions = if stage == StartupStage::Failed {
        vec!["retry", "exit"]
    } else {
        vec![]
    };
    let _ = app.emit_to(
        "splash",
        "bookbuddy://startup-stage",
        event_for(attempt, stage, message, kind, actions),
    );
}

#[tauri::command]
fn startup_frontend_stage(
    app: AppHandle,
    runtime: State<'_, Arc<StartupRuntime>>,
    stage: String,
) -> Result<(), String> {
    let next = match stage.as_str() {
        "loadingConfiguration" => StartupStage::LoadingConfiguration,
        "initializingReact" => StartupStage::InitializingReact,
        "restoringSession" => StartupStage::RestoringSession,
        "loadingLibrary" => StartupStage::LoadingLibrary,
        _ => return Err("invalid_startup_stage".into()),
    };
    let current = runtime.current_stage();
    if current == StartupStage::Failed || next.rank() < current.rank() {
        return Err("stale_startup_stage".into());
    }
    let message = match next {
        StartupStage::RestoringSession => "Restoring workspace...",
        StartupStage::LoadingLibrary => "Loading library...",
        _ => "Preparing interface...",
    };
    if next == StartupStage::LoadingLibrary {
        runtime.log(
            runtime.current_attempt(),
            StartupStage::RestoringSession,
            "state_restored",
            None,
        );
    }
    emit_event(
        &app,
        &runtime,
        event_for(runtime.current_attempt(), next, message, "progress", vec![]),
    );
    Ok(())
}

#[tauri::command]
fn startup_frontend_failed(app: AppHandle, runtime: State<'_, Arc<StartupRuntime>>, code: String) {
    let stable_code = if code == "frontend_contract_invalid" {
        "frontend_contract_invalid"
    } else {
        "frontend_initialization_failed"
    };
    fail_startup(
        &app,
        &runtime,
        runtime.current_attempt(),
        "Preparing interface...",
        stable_code,
    );
}

#[tauri::command]
fn startup_frontend_ready(
    app: AppHandle,
    runtime: State<'_, Arc<StartupRuntime>>,
) -> Result<(), String> {
    let attempt = runtime.current_attempt();
    if runtime.current_stage() != StartupStage::LoadingLibrary {
        return Err("startup_not_ready_for_handoff".into());
    }
    if runtime.transition_started.swap(true, Ordering::SeqCst) {
        return Ok(());
    }
    runtime.log(attempt, StartupStage::Ready, "library_ready", None);
    emit_event(
        &app,
        &runtime,
        event_for(attempt, StartupStage::Ready, "Ready", "ready", vec![]),
    );
    let main = app
        .get_webview_window("main")
        .ok_or_else(|| "main_window_missing".to_string())?;
    main.show().map_err(|error| error.to_string())?;
    runtime.log(attempt, StartupStage::Transition, "main_shown", None);
    emit_event(
        &app,
        &runtime,
        event_for(attempt, StartupStage::Transition, "Ready", "ready", vec![]),
    );
    let _ = app.emit_to("splash", "bookbuddy://begin-transition", ());
    let fallback_app = app.clone();
    let fallback_runtime = runtime.inner().clone();
    thread::spawn(move || {
        thread::sleep(Duration::from_millis(250));
        complete_handoff(&fallback_app, &fallback_runtime, attempt);
    });
    Ok(())
}

#[tauri::command]
fn startup_splash_faded(app: AppHandle, runtime: State<'_, Arc<StartupRuntime>>) {
    complete_handoff(&app, &runtime, runtime.current_attempt());
}

#[tauri::command]
fn startup_retry(app: AppHandle, runtime: State<'_, Arc<StartupRuntime>>) {
    if runtime.backend_healthy.load(Ordering::SeqCst) {
        start_frontend_retry(app, runtime.inner().clone());
    } else {
        start_full_attempt(app, runtime.inner().clone());
    }
}

#[tauri::command]
fn startup_exit(app: AppHandle, runtime: State<'_, Arc<StartupRuntime>>) {
    stop_backend(&runtime);
    app.exit(1);
}

#[tauri::command]
async fn upload_epub(
    path: String,
    connection: BackendConnection,
    session_name: String,
) -> Result<serde_json::Value, String> {
    let source = Path::new(&path);
    if !source.is_file()
        || source
            .extension()
            .and_then(|value| value.to_str())
            .map(|value| value.eq_ignore_ascii_case("epub"))
            != Some(true)
    {
        return Err("Choose a valid EPUB file.".into());
    }
    let file_name = source
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or("Invalid EPUB filename")?
        .to_string();
    let file_length = tokio::fs::metadata(source)
        .await
        .map_err(|error| error.to_string())?
        .len();
    let file = tokio::fs::File::open(source)
        .await
        .map_err(|error| error.to_string())?;
    let body = reqwest::Body::wrap_stream(tokio_util::codec::FramedRead::new(
        file,
        tokio_util::codec::BytesCodec::new(),
    ));
    let part = reqwest::multipart::Part::stream_with_length(body, file_length)
        .file_name(file_name)
        .mime_str("application/epub+zip")
        .map_err(|error| error.to_string())?;
    let form = reqwest::multipart::Form::new()
        .text("session_name", session_name)
        .part("file", part);
    let client = reqwest::Client::new();
    let mut request = client
        .post(format!("{}/upload", connection.base_url))
        .multipart(form);
    if let Some(token) = connection.token {
        request = request.bearer_auth(token);
    }
    let response = request.send().await.map_err(|error| error.to_string())?;
    let status = response.status();
    let payload = response
        .json::<serde_json::Value>()
        .await
        .map_err(|error| error.to_string())?;
    if !status.is_success() {
        return Err(payload
            .get("detail")
            .map(ToString::to_string)
            .unwrap_or_else(|| format!("Upload failed ({status})")));
    }
    Ok(payload)
}

#[tauri::command]
fn hide_to_tray(window: WebviewWindow) -> Result<(), String> {
    window.hide().map_err(|error| error.to_string())
}

#[tauri::command]
fn exit_app(app: AppHandle, runtime: State<'_, Arc<StartupRuntime>>) {
    stop_backend(&runtime);
    app.exit(0);
}

#[tauri::command]
fn append_performance_sample(operation: String, duration_ms: f64) -> Result<(), String> {
    const OPERATIONS: &[&str] = &[
        "cold_start",
        "reader_open",
        "resume",
        "page_turn",
        "theme_reflow",
        "selection_toolbar",
        "dictionary_cached",
        "indexed_search",
        "import_5mb",
        "home_interaction",
        "annotation_save",
    ];
    if !OPERATIONS.contains(&operation.as_str())
        || !duration_ms.is_finite()
        || !(0.0..=300_000.0).contains(&duration_ms)
    {
        return Err("invalid_performance_sample".into());
    }
    let layout = prepare_data_layout().map_err(|_| "app_directory_create_failed")?;
    let path = layout.logs.join("performance-samples.jsonl");
    let timestamp_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let record = serde_json::json!({"schema_version":"bookbuddy_performance_sample_v1","operation":operation,"duration_ms":duration_ms,"timestamp_ms":timestamp_ms});
    let line = serde_json::to_string(&record).map_err(|_| "performance_sample_serialize_failed")?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|_| "performance_sample_write_failed")?;
    writeln!(file, "{line}").map_err(|_| "performance_sample_write_failed".to_string())
}

#[tauri::command]
fn portable_config_file(filename: String) -> Result<String, String> {
    if !matches!(
        filename.as_str(),
        "reader_settings.json" | "reader-state.json" | ".window-state.json"
    ) {
        return Err("invalid_config_filename".into());
    }
    let layout = prepare_data_layout().map_err(|_| "app_directory_create_failed")?;
    Ok(layout.config.join(filename).to_string_lossy().into_owned())
}

fn safe_export_name(value: &str) -> String {
    let leaf = Path::new(value)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("bookbuddy-export.txt");
    let cleaned: String = leaf
        .chars()
        .map(|character| {
            if character.is_alphanumeric() || matches!(character, ' ' | '.' | '-' | '_') {
                character
            } else {
                '_'
            }
        })
        .collect();
    let trimmed = cleaned
        .trim_matches(|character: char| character == '.' || character == ' ' || character == '_');
    if trimmed.is_empty() {
        "bookbuddy-export.txt".into()
    } else {
        trimmed.chars().take(160).collect()
    }
}

#[tauri::command]
fn save_text_export(filename: String, contents: String) -> Result<String, String> {
    if contents.len() > 20 * 1024 * 1024 {
        return Err("export_too_large".into());
    }
    let layout = prepare_data_layout().map_err(|_| "app_directory_create_failed")?;
    let safe = safe_export_name(&filename);
    let mut target = layout.exports.join(&safe);
    if target.exists() {
        let stem = Path::new(&safe)
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("bookbuddy-export");
        let extension = Path::new(&safe)
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("txt");
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        target = layout
            .exports
            .join(format!("{stem}-{timestamp}.{extension}"));
    }
    let temporary = target.with_extension(format!(
        "{}.tmp",
        target
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("txt")
    ));
    fs::write(&temporary, contents).map_err(|_| "export_write_failed")?;
    fs::rename(&temporary, &target).map_err(|_| "export_commit_failed")?;
    Ok(target.to_string_lossy().into_owned())
}

pub fn run() {
    if relocate_portable_executable().unwrap_or(false) {
        return;
    }
    if std::env::args_os().any(|argument| argument == "--portable-smoke") {
        let layout = prepare_data_layout().expect("BookBuddy portable data directory unavailable");
        materialize_embedded_backend(&layout)
            .expect("BookBuddy embedded backend extraction failed");
        return;
    }
    let initial_layout =
        prepare_data_layout().expect("BookBuddy portable data directory unavailable");
    let window_state_file = initial_layout
        .config
        .join(".window-state.json")
        .to_string_lossy()
        .into_owned();
    let app_started = Instant::now();
    let flags =
        StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED | StateFlags::FULLSCREEN;
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_state_flags(flags)
                .with_filename(window_state_file)
                .with_denylist(&["splash"])
                .build(),
        )
        .on_window_event(|window, event| {
            if window.label() != "splash"
                || !matches!(event, tauri::WindowEvent::CloseRequested { .. })
            {
                return;
            }
            let app = window.app_handle();
            if let Some(runtime) = app.try_state::<Arc<StartupRuntime>>() {
                if runtime.handoff_complete.load(Ordering::SeqCst) {
                    return;
                }
                runtime.log(
                    runtime.current_attempt(),
                    runtime.current_stage(),
                    "splash_close_requested",
                    None,
                );
                stop_backend(&runtime);
            }
            app.exit(0);
        })
        .setup(move |app| {
            let layout = prepare_data_layout()?;
            let runtime = Arc::new(StartupRuntime::new(
                layout.logs.join("startup-timings.jsonl"),
                app_started,
            ));
            runtime.log(0, StartupStage::Launching, "process_entry", None);
            app.manage(runtime.clone());
            let handle = app.handle().clone();
            let tray_handle = handle.clone();
            let mut tray = TrayIconBuilder::new()
                .tooltip("BookBuddy")
                .on_tray_icon_event(move |_tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        if let Some(window) = tray_handle.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;
            start_full_attempt(handle, runtime);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            backend_connection,
            startup_splash_ready,
            startup_frontend_stage,
            startup_frontend_failed,
            startup_frontend_ready,
            startup_splash_faded,
            startup_retry,
            startup_exit,
            upload_epub,
            hide_to_tray,
            exit_app,
            append_performance_sample,
            portable_config_file,
            save_text_export
        ])
        .build(tauri::generate_context!())
        .expect("BookBuddy desktop failed");
    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            if let Some(runtime) = app_handle.try_state::<Arc<StartupRuntime>>() {
                stop_backend(&runtime);
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn health_contract_requires_ready_library() {
        let valid = HealthPayload {
            schema_version: "bookbuddy_health_v1".into(),
            status: "ready".into(),
            storage: HealthStorage {
                library: "available".into(),
            },
        };
        assert_eq!(validate_health(&valid), Ok(()));
        let unavailable = HealthPayload {
            storage: HealthStorage {
                library: "unavailable".into(),
            },
            ..valid
        };
        assert_eq!(
            validate_health(&unavailable),
            Err("backend_library_unavailable")
        );
    }

    #[test]
    fn startup_stages_are_monotonic_and_progress_is_not_percentage_based() {
        assert!(StartupStage::StartingBackend.rank() < StartupStage::BackendHealthy.rank());
        assert!(StartupStage::RestoringSession.rank() < StartupStage::Ready.rank());
        assert_eq!(
            StartupStage::Ready.completed_stages(),
            TOTAL_PROGRESS_STAGES
        );
    }

    #[test]
    fn splash_can_be_closed_and_does_not_cover_other_applications() {
        let config: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let splash = &config["app"]["windows"][0];
        assert_eq!(splash["label"], "splash");
        assert_eq!(splash["closable"], true);
        assert_eq!(splash["alwaysOnTop"], false);
        assert_eq!(splash["skipTaskbar"], false);
    }

    #[test]
    fn timing_log_rotates_without_copying_payload_data() {
        let directory =
            std::env::temp_dir().join(format!("bookbuddy-startup-test-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join("startup-timings.jsonl");
        fs::write(&path, vec![b'x'; LOG_ROTATE_BYTES as usize]).unwrap();
        rotate_log(&path);
        assert!(path.with_extension("jsonl.1").is_file());
        let _ = fs::remove_dir_all(directory);
    }

    #[test]
    fn local_data_layout_migrates_a_verified_copy_and_preserves_legacy_data() {
        let directory =
            std::env::temp_dir().join(format!("bookbuddy-layout-test-{}", uuid::Uuid::new_v4()));
        let legacy = directory.join("legacy-library");
        fs::create_dir_all(legacy.join("Book").join("Reading")).unwrap();
        fs::write(
            legacy.join("Book").join("Reading").join("book.epub"),
            b"epub-bytes",
        )
        .unwrap();
        let layout = create_data_layout(directory.join("BookBuddy"), Some(&legacy)).unwrap();
        assert_eq!(
            fs::read(
                layout
                    .library
                    .join("Book")
                    .join("Reading")
                    .join("book.epub")
            )
            .unwrap(),
            b"epub-bytes"
        );
        assert!(legacy
            .join("Book")
            .join("Reading")
            .join("book.epub")
            .is_file());
        for path in [
            layout.database,
            layout.logs,
            layout.cache,
            layout.config,
            layout.exports,
            layout.runtime,
        ] {
            assert!(path.is_dir());
        }
        let _ = fs::remove_dir_all(directory);
    }

    #[test]
    fn portable_folder_detection_is_case_insensitive() {
        assert!(is_bookbuddy_directory(Path::new(
            "C:/Users/Reader/BookBuddy"
        )));
        assert!(is_bookbuddy_directory(Path::new(
            "C:/Users/Reader/bookbuddy"
        )));
        assert!(!is_bookbuddy_directory(Path::new(
            "C:/Users/Reader/Downloads"
        )));
    }

    #[test]
    fn performance_samples_reject_unknown_or_invalid_values() {
        assert_eq!(
            append_performance_sample("unknown".into(), 10.0),
            Err("invalid_performance_sample".into())
        );
        assert_eq!(
            append_performance_sample("page_turn".into(), f64::NAN),
            Err("invalid_performance_sample".into())
        );
    }

    #[test]
    fn export_names_cannot_escape_the_exports_directory() {
        assert_eq!(safe_export_name("..\\..\\notes.md"), "notes.md");
        assert_eq!(safe_export_name("bad:name?.md"), "bad_name_.md");
    }
}
