// src-tauri/src/main.rs
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

fn start_backend(app_handle: &tauri::AppHandle) -> std::io::Result<Child> {
    // Em produção, o executável Python fica na pasta de recursos do app
    let resource_dir = app_handle
        .path()
        .resource_dir()
        .expect("Não foi possível obter resource_dir");

    // O backend é empacotado como executável standalone pelo PyInstaller
    let backend_exe = resource_dir.join("backend").join(if cfg!(windows) {
        "yt-dlp-backend.exe"
    } else {
        "yt-dlp-backend"
    });

    Command::new(backend_exe).spawn()
}

fn main() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            // Inicia o servidor Python ao abrir o app
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
            // Encerra o backend ao fechar a janela
            if let tauri::WindowEvent::Destroyed = event {
                let state: State<BackendProcess> = window.state();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    child.kill().ok();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_downloads_dir,
            open_folder,
        ])
        .run(tauri::generate_context!())
        .expect("Erro ao iniciar yt-dlp-GUI");
}
