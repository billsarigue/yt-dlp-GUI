#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, State};

// CREATE_NO_WINDOW só existe no Windows
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const CREATE_NO_WINDOW: u32 = 0x08000000;

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
    #[cfg(debug_assertions)]
    {
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let backend_script = std::path::Path::new(manifest_dir)
            .parent().unwrap()
            .join("backend")
            .join("main.py");

        let mut cmd = Command::new("python");
        cmd.arg(backend_script);
        #[cfg(target_os = "windows")]
        cmd.creation_flags(CREATE_NO_WINDOW);
        return cmd.spawn();
    }

    #[cfg(not(debug_assertions))]
    {
        let exe_dir = std::env::current_exe()
            .expect("Não foi possível obter o caminho do executável")
            .parent()
            .expect("Não foi possível obter o diretório do executável")
            .to_path_buf();

        let backend_exe = exe_dir.join(if cfg!(windows) {
            "yt-dlp-backend.exe"
        } else {
            "yt-dlp-backend"
        });

        let mut cmd = Command::new(&backend_exe);
        #[cfg(target_os = "windows")]
        cmd.creation_flags(CREATE_NO_WINDOW);
        cmd.spawn()
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
                if let Some(ref mut c) = state.0.lock().unwrap().take() {
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
