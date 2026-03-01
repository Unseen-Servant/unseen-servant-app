use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

#[derive(Serialize, Deserialize, Debug, Clone)]
struct FileItem {
    name: String,
    path: String,
    is_dir: bool,
    children: Option<Vec<FileItem>>,
}

#[tauri::command]
async fn select_folder(app: tauri::AppHandle) -> Result<String, String> {
    use tauri_plugin_dialog::DialogExt;

    let folder = app.dialog()
        .file()
        .set_title("Select your TTRPG folder")
        .blocking_pick_folder();

    match folder {
        Some(path) => Ok(path.to_string()),
        None => Err("No folder selected".to_string()),
    }
}

#[tauri::command]
fn list_files(folder_path: String) -> Result<Vec<FileItem>, String> {
    let mut items = Vec::new();
    let folder = Path::new(&folder_path);

    if !folder.is_dir() {
        return Err("Path is not a directory".to_string());
    }

    for entry in fs::read_dir(folder).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let metadata = entry.metadata().map_err(|e| e.to_string())?;
        let file_type = metadata.file_type();
        let is_dir = file_type.is_dir();
        let name = entry.file_name().to_string_lossy().into_owned();
        let path = folder.join(&name).to_string_lossy().into_owned();
        let is_pdf = !is_dir && name.to_lowercase().ends_with(".pdf");

        if is_dir || is_pdf {
            items.push(FileItem { 
                name, 
                path, 
                is_dir,
                children: None,
            });
        }
    }

    Ok(items)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![select_folder, list_files])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
