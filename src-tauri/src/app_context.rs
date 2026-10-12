//! Workstation context every panel shares: the active campaign and session.
//!
//! Each window is its own JS context, so Rust is the source of truth. A
//! window pulls the snapshot with `get_app_context` when it mounts and follows
//! `app-context://changed` after that; the setters broadcast to every window,
//! the caller included, and to the sidecar, so Command's MCP tools act on
//! what's open with no window needed (`command::push_context`).

use serde::Serialize;
use std::sync::{Mutex, PoisonError};
use tauri::async_runtime::Mutex as AsyncMutex;
use tauri::{AppHandle, Emitter, Manager};

pub const CHANGED_EVENT: &str = "app-context://changed";

#[derive(Serialize, Clone, Debug, Default, PartialEq)]
pub struct AppContextSnapshot {
    /// Bumped on every change, so a window can drop a pulled snapshot that
    /// lands after a newer pushed one.
    seq: u64,
    campaign: Option<String>,
    session: Option<String>,
}

#[derive(Default)]
pub struct AppContext {
    snap: Mutex<AppContextSnapshot>,
    /// Held across a whole campaign change, the discard of the campaign left
    /// behind included (`command::discard_if_blank`): otherwise a New campaign
    /// right after leaving a blank Untitled could be handed that same folder
    /// just before the discard removes it.
    switching: AsyncMutex<()>,
}

/// What a campaign switch changed: the snapshot to broadcast, and the
/// campaign left behind, if there was one.
pub(crate) struct Switched {
    snap: AppContextSnapshot,
    left: Option<String>,
}

/// A blank name is no name: the picker's "none" may arrive as "".
fn normalize(name: Option<String>) -> Option<String> {
    name.map(|n| n.trim().to_string()).filter(|n| !n.is_empty())
}

impl AppContext {
    pub(crate) fn snapshot(&self) -> AppContextSnapshot {
        self.snap
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    /// The open campaign, for commands that act on it.
    pub(crate) fn campaign(&self) -> Option<String> {
        self.snapshot().campaign
    }

    /// Switch campaigns. A session belongs to its campaign, so a different
    /// campaign clears it. `None` when nothing changed, so there is nothing
    /// to emit.
    fn set_campaign(&self, campaign: Option<String>) -> Option<Switched> {
        let campaign = normalize(campaign);
        let mut snap = self.snap.lock().unwrap_or_else(PoisonError::into_inner);
        if snap.campaign == campaign {
            return None;
        }
        let left = std::mem::replace(&mut snap.campaign, campaign);
        snap.session = None;
        snap.seq += 1;
        Some(Switched {
            snap: snap.clone(),
            left,
        })
    }

    fn set_session(&self, session: Option<String>) -> Option<AppContextSnapshot> {
        let session = normalize(session);
        let mut snap = self.snap.lock().unwrap_or_else(PoisonError::into_inner);
        if snap.session == session {
            return None;
        }
        snap.session = session;
        snap.seq += 1;
        Some(snap.clone())
    }
}

fn broadcast(app: &AppHandle, changed: Option<AppContextSnapshot>) {
    if let Some(snap) = changed {
        let _ = app.emit(CHANGED_EVENT, &snap);
        crate::command::push_context(&snap);
    }
}

#[tauri::command]
pub fn get_app_context(state: tauri::State<AppContext>) -> AppContextSnapshot {
    state.snapshot()
}

/// Make `campaign` the open one in every window, then discard the campaign
/// left behind if it was an untitled one the GM left blank. With `then`, the
/// campaign to switch to is worked out under the same lock (the sidecar's
/// fresh Untitled, say), so nothing can switch in between.
pub(crate) async fn switch_campaign_with<F, Fut>(
    app: &AppHandle,
    then: F,
) -> Result<Option<String>, String>
where
    F: FnOnce() -> Fut,
    Fut: std::future::Future<Output = Result<Option<String>, String>>,
{
    let state = app.state::<AppContext>();
    let _one_at_a_time = state.switching.lock().await;
    let campaign = then().await?;
    if let Some(switched) = state.set_campaign(campaign.clone()) {
        broadcast(app, Some(switched.snap));
        crate::file_menu::spawn_refresh(app);
        if let Some(left) = switched.left {
            crate::command::discard_if_blank(&left).await;
        }
    }
    Ok(campaign)
}

#[tauri::command]
pub async fn set_active_campaign(app: AppHandle, campaign: Option<String>) -> Result<(), String> {
    switch_campaign_with(&app, || async { Ok(campaign) })
        .await
        .map(|_| ())
}

#[tauri::command]
pub fn set_active_session(
    app: AppHandle,
    state: tauri::State<AppContext>,
    session: Option<String>,
) {
    broadcast(&app, state.set_session(session));
}

#[cfg(test)]
mod tests {
    use super::*;

    fn some(name: &str) -> Option<String> {
        Some(name.to_string())
    }

    #[test]
    fn starts_with_no_campaign_and_no_session() {
        assert_eq!(
            AppContext::default().snapshot(),
            AppContextSnapshot::default()
        );
    }

    #[test]
    fn set_campaign_reports_only_changes_and_bumps_seq() {
        let ctx = AppContext::default();
        let first = ctx.set_campaign(some("Curse of Strahd")).unwrap().snap;
        assert_eq!(first.seq, 1);
        assert_eq!(first.campaign.as_deref(), Some("Curse of Strahd"));
        assert!(ctx.set_campaign(some("Curse of Strahd")).is_none());
        let second = ctx.set_campaign(some("Into the Odd")).unwrap().snap;
        assert_eq!(second.seq, 2);
        assert_eq!(ctx.snapshot(), second);
    }

    #[test]
    fn set_session_reports_only_changes_and_bumps_seq() {
        let ctx = AppContext::default();
        ctx.set_campaign(some("Curse of Strahd"));
        let snap = ctx.set_session(some("Session 12")).unwrap();
        assert_eq!(snap.seq, 2);
        assert_eq!(snap.session.as_deref(), Some("Session 12"));
        assert!(ctx.set_session(some("Session 12")).is_none());
        assert_eq!(ctx.snapshot().seq, 2);
    }

    #[test]
    fn a_different_campaign_clears_the_session() {
        let ctx = AppContext::default();
        ctx.set_campaign(some("Curse of Strahd"));
        ctx.set_session(some("Session 12"));
        let snap = ctx.set_campaign(some("Into the Odd")).unwrap().snap;
        assert_eq!(snap.session, None);
    }

    #[test]
    fn the_same_campaign_keeps_the_session() {
        let ctx = AppContext::default();
        ctx.set_campaign(some("Curse of Strahd"));
        ctx.set_session(some("Session 12"));
        assert!(ctx.set_campaign(some("  Curse of Strahd ")).is_none());
        assert_eq!(ctx.snapshot().session.as_deref(), Some("Session 12"));
    }

    #[test]
    fn clearing_the_campaign_clears_both() {
        let ctx = AppContext::default();
        ctx.set_campaign(some("Curse of Strahd"));
        ctx.set_session(some("Session 12"));
        let snap = ctx.set_campaign(None).unwrap().snap;
        assert_eq!((snap.campaign, snap.session), (None, None));
    }

    #[test]
    fn blank_names_mean_none() {
        let ctx = AppContext::default();
        assert!(ctx.set_campaign(some("   ")).is_none());
        assert!(ctx.set_session(some("")).is_none());
        ctx.set_campaign(some("Curse of Strahd"));
        let snap = ctx.set_campaign(some("")).unwrap().snap;
        assert_eq!(snap.campaign, None);
    }

    #[test]
    fn a_session_does_not_require_a_campaign() {
        let ctx = AppContext::default();
        let snap = ctx.set_session(some("One-shot")).unwrap();
        assert_eq!(
            (snap.campaign, snap.session.as_deref()),
            (None, Some("One-shot"))
        );
    }

    #[test]
    fn a_switch_reports_the_campaign_left() {
        let ctx = AppContext::default();
        assert_eq!(ctx.set_campaign(some("Untitled")).unwrap().left, None);
        let switched = ctx.set_campaign(some("Curse of Strahd")).unwrap();
        assert_eq!(switched.left.as_deref(), Some("Untitled"));
        assert_eq!(
            ctx.set_campaign(None).unwrap().left.as_deref(),
            Some("Curse of Strahd")
        );
    }
}
