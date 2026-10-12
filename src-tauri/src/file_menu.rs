//! The macOS File menu: Command's campaigns, as the switcher in its bar
//! offers them (design §3.7), for when Command isn't the window in front.
//!
//! Built on Tauri's default menu, so Edit, View and Window keep their
//! standard items and File keeps Close Window below the campaign items.
//! macOS only: elsewhere an app menu is a bar inside every window, and the
//! switcher already does the job.

// Installed only on macOS; the rest compiles everywhere and does nothing
// without it, which Linux CI's clippy would otherwise call dead code.
#![cfg_attr(not(target_os = "macos"), allow(dead_code))]

use std::sync::{Mutex, PoisonError};
use tauri::menu::{CheckMenuItem, Menu, MenuItem, MenuItemKind, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Manager, Wry};
use tauri_plugin_opener::OpenerExt;

use crate::app_context::{switch_campaign_with, AppContext};

const NEW: &str = "campaign.new";
const OPEN: &str = "campaign.open";
const OPEN_PREFIX: &str = "campaign.open:";
const SHOW_FOLDER: &str = "campaign.folder.show";
const CHANGE_FOLDER: &str = "campaign.folder.change";

/// Open Campaign ▸, rebuilt whenever the campaigns or the open one change.
/// The lock keeps two rebuilds from interleaving their rows.
pub struct FileMenu(Mutex<Submenu<Wry>>);

/// Set the app menu: the default one, with the campaign items at the top
/// of File.
pub fn install(app: &AppHandle) -> tauri::Result<()> {
    let menu = Menu::default(app)?;
    let open = Submenu::with_id(app, OPEN, "Open Campaign", true)?;
    let file = menu.items()?.into_iter().find_map(|item| match item {
        MenuItemKind::Submenu(s) if s.text().is_ok_and(|t| t == "File") => Some(s),
        _ => None,
    });
    if let Some(file) = file {
        file.insert_items(
            &[
                // ⌘N is Legend Lore's new collection, and a menu shortcut
                // would take it from every window.
                &MenuItem::with_id(app, NEW, "New Campaign", true, Some("Shift+Cmd+N"))?,
                &open,
                &PredefinedMenuItem::separator(app)?,
                &MenuItem::with_id(
                    app,
                    SHOW_FOLDER,
                    "Show Campaigns Folder",
                    true,
                    None::<&str>,
                )?,
                &MenuItem::with_id(
                    app,
                    CHANGE_FOLDER,
                    "Change Campaigns Folder…",
                    true,
                    None::<&str>,
                )?,
                &PredefinedMenuItem::separator(app)?,
            ],
            0,
        )?;
    }
    app.set_menu(menu)?;
    app.manage(FileMenu(Mutex::new(open)));
    Ok(())
}

/// Rebuild Open Campaign from the campaigns folder, the open one ticked.
/// Does nothing where the menu isn't installed.
pub async fn refresh(app: &AppHandle) {
    if app.try_state::<FileMenu>().is_none() {
        return;
    }
    let campaigns = crate::command::command_list_campaigns()
        .await
        .unwrap_or_default();
    let open = app.state::<AppContext>().campaign();
    let menu = app.state::<FileMenu>();
    let submenu = menu.0.lock().unwrap_or_else(PoisonError::into_inner);
    if let Err(e) = rebuild(app, &submenu, &campaigns, open.as_deref()) {
        eprintln!("File menu: couldn't list the campaigns: {}", e);
    }
}

fn rebuild(
    app: &AppHandle,
    submenu: &Submenu<Wry>,
    campaigns: &[String],
    open: Option<&str>,
) -> tauri::Result<()> {
    while submenu.remove_at(0)?.is_some() {}
    if campaigns.is_empty() {
        return submenu.append(&MenuItem::new(app, "No campaigns", false, None::<&str>)?);
    }
    for name in campaigns {
        submenu.append(&CheckMenuItem::with_id(
            app,
            format!("{OPEN_PREFIX}{name}"),
            name,
            true,
            open == Some(name.as_str()),
            None::<&str>,
        )?)?;
    }
    Ok(())
}

pub fn spawn_refresh(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move { refresh(&app).await });
}

/// Handle a click on one of the campaign items. Other ids pass through.
pub fn on_event(app: &AppHandle, id: &str) {
    let app = app.clone();
    if id == NEW {
        tauri::async_runtime::spawn(async move {
            report(crate::command::open_untitled(&app).await);
            crate::panels::show_panel(&app, "command");
        });
    } else if let Some(name) = id.strip_prefix(OPEN_PREFIX) {
        let name = name.to_string();
        tauri::async_runtime::spawn(async move {
            report(switch_campaign_with(&app, || async { Ok(Some(name)) }).await);
            // A click flips a check item's tick by itself, the open
            // campaign's included: set every tick back from the context.
            refresh(&app).await;
            crate::panels::show_panel(&app, "command");
        });
    } else if id == SHOW_FOLDER {
        tauri::async_runtime::spawn(async move {
            let shown = match crate::command::command_get_settings().await {
                Ok(settings) => match settings.root {
                    Some(root) => app
                        .opener()
                        .open_path(root, None::<&str>)
                        .map_err(|e| e.to_string()),
                    None => Err("No campaigns folder is set".to_string()),
                },
                Err(e) => Err(e),
            };
            report(shown);
        });
    } else if id == CHANGE_FOLDER {
        tauri::async_runtime::spawn(async move {
            report(crate::command::command_choose_root(app.clone()).await);
        });
    }
}

fn report<T>(outcome: Result<T, String>) {
    if let Err(e) = outcome {
        eprintln!("File menu: {}", e);
    }
}
