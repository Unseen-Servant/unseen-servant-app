<script lang="ts">
  import { chord, commitKeyShortcut } from './keybindings';
  import { commitKeyId } from './confirmKeys';

  export let label: string;
  // Removal (delete, reset) vs activation (re-index). The app's colour law:
  // a mode you switched on is purple and lit; a removal is danger-tinted and
  // deliberately unlit, because a glow marks an activation and a removal is
  // not one.
  export let danger: boolean = false;
  export let disabled: boolean = false;
  export let onClick: () => void = () => {};
  // Marks this as the unit's initial focus target. Modal.svelte queries for
  // [data-autofocus] after showModal(), so it has to be in the markup.
  export let initialFocus: boolean = false;

  // The face carries the key that throws it — the rule the scope bar's bypass
  // already follows. Read from KEYBINDINGS so the glyph has one definition.
  $: face = chord(commitKeyId(danger));

  // aria-keyshortcuts names shortcuts *an author has implemented* (per its
  // spec). A removal prompt's ⌘⌫ is one — ConfirmDialog's own keydown handler
  // implements it. An activation prompt's Enter is not: that is native
  // <button> activation, which answers Space equally, so naming Enter alone
  // would both describe built-in behaviour and imply Enter is special. Omit
  // the attribute there rather than deriving it from confirm.commitSafe —
  // that binding exists only to supply the face glyph, and deriving from it
  // would assert a dependency that does not exist.
  $: ariaKeys = danger ? commitKeyShortcut() : undefined;
</script>

<button
  type="button"
  class="commit-switch"
  class:danger
  class:activation={!danger}
  {disabled}
  data-autofocus={initialFocus || undefined}
  aria-keyshortcuts={ariaKeys}
  on:click={onClick}
  on:keydown={(e) => {
    // The sibling of ConfirmDialog's repeat guard, for the commit the browser
    // fires rather than us. Holding Enter on a menu row opens an activation
    // prompt whose switch takes focus inside the OS repeat delay; the next
    // repeat keydown is then a synthesized click on this button, answering a
    // question that was never on screen long enough to read. preventDefault
    // on keydown cancels that synthesized activation for Enter and Space
    // alike. It lives here because every commit in the app is this component,
    // and because no handler in the dialog can reach a click the browser
    // makes for us.
    if (e.repeat) e.preventDefault();
  }}
>
  <span class="commit-label">{label}</span>
  <!-- A span, not a button: a nested button is illegal, and the face is not
       independently operable — pressing anywhere on the pair fires it. -->
  <span class="switch-face" aria-hidden="true">{face}</span>
</button>
