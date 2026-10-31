//! Panel pop-out: any tool panel docked in the main window can open in its own
//! window and dock back (contract: `src/lib/shell/PANELS.md`).
//!
//! Rust owns which panels are popped out, so a panel is never live in two
//! windows: the main window shows a placeholder in its tab instead. Windows
//! pull the set with `get_popped_panels` when they mount and follow
//! `panels://changed` after that. A pop-out leaves the set only when its
//! window is destroyed — the dock-back action and the OS close button both
//! end there.

use serde::Serialize;
use std::collections::BTreeSet;
use std::sync::{Mutex, PoisonError};
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

pub const CHANGED_EVENT: &str = "panels://changed";
/// To the main window: bring this panel forward in the rack (`show_panel`).
pub const SHOW_EVENT: &str = "panels://show";
const LABEL_PREFIX: &str = "panel-";

struct PanelSpec {
    id: &'static str,
    title: &'static str,
    size: (f64, f64),
    min_size: (f64, f64),
}

/// The frontend's manifest (`src/lib/shell/panels.ts`) carries the same ids;
/// window defaults live here because Rust creates the windows.
const PANELS: [PanelSpec; 4] = [
    PanelSpec {
        id: "legend-lore",
        title: "Legend Lore",
        size: (1280.0, 800.0),
        min_size: (940.0, 600.0),
    },
    PanelSpec {
        id: "command",
        title: "Command",
        size: (720.0, 560.0),
        min_size: (420.0, 320.0),
    },
    // Compact (panels.ts): it opens at its smallest, the rack's 270×356 plus
    // the pop-out's status bar.
    PanelSpec {
        id: "augury",
        title: "Augury",
        size: (270.0, 384.0),
        min_size: (270.0, 384.0),
    },
    PanelSpec {
        id: "servant",
        title: "Servant",
        size: (560.0, 640.0),
        min_size: (380.0, 320.0),
    },
];

fn spec(id: &str) -> Result<&'static PanelSpec, String> {
    PANELS
        .iter()
        .find(|p| p.id == id)
        .ok_or_else(|| format!("Unknown panel: {id}"))
}

fn label_of(id: &str) -> String {
    format!("{LABEL_PREFIX}{id}")
}

/// The panel a window label belongs to, or `None` for any other window.
pub fn panel_of_label(label: &str) -> Option<&'static str> {
    let id = label.strip_prefix(LABEL_PREFIX)?;
    spec(id).ok().map(|p| p.id)
}

#[derive(Serialize, Clone, Debug, Default, PartialEq)]
pub struct PanelsSnapshot {
    /// Bumped on every change, so a window can drop a pulled snapshot that
    /// lands after a newer pushed one.
    seq: u64,
    popped: BTreeSet<&'static str>,
}

#[derive(Default)]
pub struct PoppedPanels(Mutex<PanelsSnapshot>);

impl PoppedPanels {
    fn snapshot(&self) -> PanelsSnapshot {
        self.0
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    /// `None` when nothing changed, so there is nothing to emit.
    fn insert(&self, id: &'static str) -> Option<PanelsSnapshot> {
        let mut snap = self.0.lock().unwrap_or_else(PoisonError::into_inner);
        if !snap.popped.insert(id) {
            return None;
        }
        snap.seq += 1;
        Some(snap.clone())
    }

    fn remove(&self, id: &str) -> Option<PanelsSnapshot> {
        let mut snap = self.0.lock().unwrap_or_else(PoisonError::into_inner);
        if !snap.popped.remove(id) {
            return None;
        }
        snap.seq += 1;
        Some(snap.clone())
    }
}

fn broadcast(app: &AppHandle, changed: Option<PanelsSnapshot>) {
    if let Some(snap) = changed {
        let _ = app.emit(CHANGED_EVENT, &snap);
    }
}

#[tauri::command]
pub fn get_popped_panels(state: tauri::State<PoppedPanels>) -> PanelsSnapshot {
    state.snapshot()
}

/// Open a panel in its own window, or bring that window forward if it is
/// already out.
///
/// Async because building a window from a synchronous command deadlocks on
/// Windows.
#[tauri::command]
pub async fn pop_out_panel(app: AppHandle, id: String) -> Result<(), String> {
    let spec = spec(&id)?;
    let label = label_of(spec.id);
    if let Some(window) = app.get_webview_window(&label) {
        let _ = window.unminimize();
        let _ = window.set_focus();
        return Ok(());
    }
    let (width, height) = spec.size;
    let (min_width, min_height) = spec.min_size;
    WebviewWindowBuilder::new(
        &app,
        &label,
        WebviewUrl::App(format!("panel/{}", spec.id).into()),
    )
    .title(spec.title)
    .inner_size(width, height)
    .min_inner_size(min_width, min_height)
    // As on the main window: Tauri's file-drop handler would swallow the
    // HTML5 drag-and-drop the file tree uses.
    .disable_drag_drop_handler()
    .build()
    .map_err(|e| format!("Failed to open the {} window: {e}", spec.title))?;
    broadcast(&app, app.state::<PoppedPanels>().insert(spec.id));
    Ok(())
}

/// Close a panel's own window and bring the main window forward; the panel
/// reappears in its tab once the window is gone (`on_window_destroyed`).
#[tauri::command]
pub fn dock_panel(app: AppHandle, id: String) -> Result<(), String> {
    let spec = spec(&id)?;
    if let Some(window) = app.get_webview_window(&label_of(spec.id)) {
        window.destroy().map_err(|e| e.to_string())?;
    }
    crate::show_tool_window(&app);
    Ok(())
}

/// Bring a panel to the GM: its own window when it's out, else the main
/// window with the panel brought forward in its rack (PanelHost follows
/// `SHOW_EVENT`).
pub fn show_panel(app: &AppHandle, id: &str) {
    if let Some(window) = app.get_webview_window(&label_of(id)) {
        let _ = window.unminimize();
        let _ = window.set_focus();
        return;
    }
    crate::show_tool_window(app);
    let _ = app.emit_to("main", SHOW_EVENT, id);
}

/// Bring forward the window holding this panel and leave the rack's view as
/// it is: the panel's own window when it's popped out, else the main one.
pub fn show_window_of(app: &AppHandle, id: &str) {
    match app.get_webview_window(&label_of(id)) {
        Some(window) => {
            let _ = window.unminimize();
            let _ = window.set_focus();
        }
        None => crate::show_tool_window(app),
    }
}

/// Called for every destroyed window; docks the panel if it was a pop-out.
pub fn on_window_destroyed(app: &AppHandle, label: &str) {
    if let Some(id) = panel_of_label(label) {
        broadcast(app, app.state::<PoppedPanels>().remove(id));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spec_rejects_an_unknown_panel() {
        assert!(spec("legend-lore").is_ok());
        assert_eq!(spec("nope").err().as_deref(), Some("Unknown panel: nope"));
    }

    #[test]
    fn panel_of_label_round_trips_and_ignores_other_windows() {
        for p in &PANELS {
            assert_eq!(panel_of_label(&label_of(p.id)), Some(p.id));
        }
        assert_eq!(panel_of_label("main"), None);
        assert_eq!(panel_of_label("splash"), None);
        assert_eq!(panel_of_label("panel-nope"), None);
        assert_eq!(panel_of_label("legend-lore"), None);
    }

    #[test]
    fn starts_with_every_panel_docked() {
        assert_eq!(
            PoppedPanels::default().snapshot(),
            PanelsSnapshot::default()
        );
    }

    #[test]
    fn insert_reports_only_changes_and_bumps_seq() {
        let panels = PoppedPanels::default();
        let first = panels.insert("command").unwrap();
        assert_eq!(first.seq, 1);
        assert!(first.popped.contains("command"));
        assert!(panels.insert("command").is_none());
        let second = panels.insert("servant").unwrap();
        assert_eq!(second.seq, 2);
        assert_eq!(second.popped.len(), 2);
    }

    #[test]
    fn remove_reports_only_changes_and_bumps_seq() {
        let panels = PoppedPanels::default();
        assert!(panels.remove("command").is_none());
        panels.insert("command");
        let snap = panels.remove("command").unwrap();
        assert_eq!(snap.seq, 2);
        assert!(snap.popped.is_empty());
        assert!(panels.remove("command").is_none());
        assert_eq!(panels.snapshot().seq, 2);
    }
}
