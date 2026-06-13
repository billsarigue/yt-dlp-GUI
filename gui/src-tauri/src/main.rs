#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, State};

struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
fn get_downloads_dir() -> String {
    dirs::download_dir()
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default())
        .to_string_lossy()
        .to_string()
}

#[tauri::command]
fn open_folder(path: String) {
    #[cfg(target_os = "windows")]
    Command::new("explorer").arg(&path).spawn().ok();
    #[cfg(target_os = "macos")]
    Command::new("open").arg(&path).spawn().ok();
    #[cfg(target_os = "linux")]
    Command::new("xdg-open").arg(&path).spawn().ok();
}

fn start_backend(_app_handle: &tauri::AppHandle) -> std::io::Result<Child> {
    // Em DEV: roda o script Python diretamente
    #[cfg(debug_assertions)]
    {
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let backend_script = std::path::Path::new(manifest_dir)
            .parent().unwrap()  // sai de src-tauri/
            .join("backend")
            .join("main.py");

        return Command::new("python3")
            .arg(backend_script)
            .spawn();
    }

    // Em PRODUÇÃO: usa o executável PyInstaller empacotado
    #[cfg(not(debug_assertions))]
    {
        let resource_dir = app_handle
            .path()
            .resource_dir()
            .expect("Não foi possível obter resource_dir");

        let backend_exe = resource_dir.join("backend").join(if cfg!(windows) {
            "yt-dlp-backend.exe"
        } else {
            "yt-dlp-backend"
        });

        Command::new(backend_exe).spawn()
    }
}

fn main() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            match start_backend(&app.handle()) {
                Ok(child) => {
                    let state: State<BackendProcess> = app.state();
                    *state.0.lock().unwrap() = Some(child);
                    println!("Backend Python iniciado.");
                }
                Err(e) => {
                    eprintln!("Erro ao iniciar backend: {e}");
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state: State<BackendProcess> = window.state();
                let mut child = state.0.lock().unwrap().take();
                if let Some(ref mut c) = child {
                    c.kill().ok();
                };
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_downloads_dir,
            open_folder,
        ])
        .run(tauri::generate_context!())
        .expect("Erro ao iniciar yt-dlp-GUI");
}