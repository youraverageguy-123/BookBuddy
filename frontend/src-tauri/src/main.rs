// Keep the native host windowless in both debug and release builds. Backend
// diagnostics are written to the app log, so a console window should never
// appear beside the reader during normal startup.
#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

fn main() {
    bookbuddy_lib::run();
}
