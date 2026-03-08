<script lang="ts">
  export let visible = false;
  export let onClose: () => void;

  const licenseText = `Legend Lore - Proprietary Software License

Copyright (c) 2026 Jerome Solis. All rights reserved.

1. GRANT OF LICENSE

   You are granted a limited, non-exclusive, non-transferable,
   revocable license to use Legend Lore (the "Software") for
   personal, non-commercial purposes, subject to the terms of
   this license.

2. RESTRICTIONS

   You may NOT, without prior written permission from the
   copyright holder:

   a. Copy, modify, adapt, or create derivative works of
      the Software or any part thereof.
   b. Distribute, sublicense, lease, rent, loan, or otherwise
      transfer the Software to any third party.
   c. Reverse engineer, decompile, disassemble, or otherwise
      attempt to derive the source code of the Software.
   d. Remove, alter, or obscure any copyright, trademark, or
      other proprietary notices in the Software.
   e. Use the Software for any commercial purpose without a
      separate commercial license.

3. OWNERSHIP

   The Software and all copies thereof are proprietary to and
   the property of Jerome Solis. All rights in the Software
   not specifically granted in this license are reserved by
   the copyright holder.

4. NO WARRANTY

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
   KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
   WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
   PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE
   COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER
   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR
   OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE
   SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

5. TERMINATION

   This license is effective until terminated. It will terminate
   automatically without notice if you fail to comply with any
   term of this license. Upon termination, you must destroy all
   copies of the Software in your possession.

6. GOVERNING LAW

   This license shall be governed by and construed in accordance
   with the laws of the Province of Quebec, Canada, without
   regard to its conflict of law provisions.

7. ENTIRE AGREEMENT

   This license constitutes the entire agreement between you and
   the copyright holder regarding the Software and supersedes all
   prior agreements and understandings, whether written or oral.

For licensing inquiries, contact: guild@unseenservant.com`;

  function handleBackdrop(e: MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }
</script>

{#if visible}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="backdrop" role="dialog" aria-modal="true" aria-label="License" on:click={handleBackdrop} on:keydown={handleKeydown}>
    <div class="modal">
      <div class="modal-header">
        <span class="modal-title font-heading">License</span>
        <button class="close-btn" on:click={onClose} aria-label="Close">&times;</button>
      </div>
      <div class="modal-body">
        <pre class="license-text">{licenseText}</pre>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .modal {
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    width: min(560px, 90vw);
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .modal-title {
    font-size: 1.1rem;
    color: var(--text-accent);
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 1.4rem;
    line-height: 1;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .close-btn:hover {
    color: var(--text-primary);
  }

  .modal-body {
    overflow-y: auto;
    padding: 1rem;
  }

  .license-text {
    margin: 0;
    white-space: pre-wrap;
    font-family: var(--font-body);
    font-size: 0.85rem;
    line-height: 1.5;
    color: var(--text-primary);
  }
</style>
