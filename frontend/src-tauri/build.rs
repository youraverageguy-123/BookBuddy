use std::{env, fs, path::PathBuf};

fn backend_fingerprint(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0xcbf29ce484222325, |hash, byte| {
        (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
    })
}

fn main() {
    let manifest_dir =
        PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").expect("missing manifest directory"));
    let backend = manifest_dir
        .join("binaries")
        .join("bookbuddy-backend-x86_64-pc-windows-msvc.exe");
    println!("cargo:rerun-if-changed={}", backend.display());
    let bytes = fs::read(&backend)
        .expect("build the BookBuddy backend sidecar before compiling the desktop app");
    println!(
        "cargo:rustc-env=BOOKBUDDY_BACKEND_FINGERPRINT={:016x}",
        backend_fingerprint(&bytes)
    );
    tauri_build::build()
}
