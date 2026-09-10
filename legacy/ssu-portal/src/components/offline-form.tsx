"use client";

import { useEffect, useRef, useState } from "react";
import { CloudOff, HardDriveDownload, WifiOff } from "lucide-react";
import { Callout } from "@/components/ui/callout";

/**
 * A form that survives losing signal.
 *
 * An application takes twenty minutes to fill in. On a 3G connection that
 * drops in and out, the default browser behaviour — lose everything on a failed
 * POST — makes the portal unusable, and applicants give up rather than start
 * again. So every keystroke is mirrored into localStorage, and submitting while
 * offline is refused loudly instead of silently discarding the work.
 *
 * Draft lifecycle:
 *   - saved on every change, debounced, under `draftKey`
 *   - restored on mount only when the local copy is NEWER than the server's
 *     `remoteUpdatedAt`, so a save from another device is not clobbered
 *   - discarded once the server has caught up
 *
 * File inputs are skipped: a File cannot be serialised, and re-picking the
 * photo is a far smaller loss than re-typing eight subject marks.
 */

interface Draft {
  savedAt: number;
  values: Record<string, string | string[]>;
}

export function OfflineForm({
  action,
  draftKey,
  remoteUpdatedAt,
  children,
  className,
}: {
  action: (formData: FormData) => void | Promise<void>;
  draftKey: string;
  /** ISO timestamp of the server's copy of this step. */
  remoteUpdatedAt: string;
  children: React.ReactNode;
  className?: string;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [online, setOnline] = useState(true);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [restored, setRestored] = useState(false);
  const [blockedOffline, setBlockedOffline] = useState(false);

  // --- Connectivity ---
  useEffect(() => {
    const sync = () => setOnline(navigator.onLine);
    sync();
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, []);

  // --- Restore, or discard a stale draft ---
  useEffect(() => {
    const form = formRef.current;
    if (!form) return;

    let draft: Draft | null = null;
    try {
      const raw = window.localStorage.getItem(draftKey);
      if (raw) draft = JSON.parse(raw) as Draft;
    } catch {
      // Private mode, or a corrupted entry. Carry on with the server's copy.
      return;
    }
    if (!draft) return;

    const remote = new Date(remoteUpdatedAt).getTime();
    if (Number.isFinite(remote) && draft.savedAt <= remote) {
      // The server already has this or something newer.
      try {
        window.localStorage.removeItem(draftKey);
      } catch {}
      return;
    }

    applyDraft(form, draft.values);
    setSavedAt(draft.savedAt);
    setRestored(true);
  }, [draftKey, remoteUpdatedAt]);

  // --- Save on change, debounced ---
  useEffect(() => {
    const form = formRef.current;
    if (!form) return;

    let timer: number | undefined;
    const save = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const draft: Draft = { savedAt: Date.now(), values: readForm(form) };
        try {
          window.localStorage.setItem(draftKey, JSON.stringify(draft));
          setSavedAt(draft.savedAt);
        } catch {
          // Quota exceeded or storage blocked. The form still works; the
          // student just loses the safety net, so say nothing rather than
          // interrupt them with an error they cannot act on.
        }
      }, 400);
    };

    form.addEventListener("input", save);
    form.addEventListener("change", save);
    return () => {
      window.clearTimeout(timer);
      form.removeEventListener("input", save);
      form.removeEventListener("change", save);
    };
  }, [draftKey]);

  return (
    <form
      ref={formRef}
      action={action}
      className={className}
      onSubmit={(event) => {
        if (!navigator.onLine) {
          event.preventDefault();
          setBlockedOffline(true);
          return;
        }
        setBlockedOffline(false);
      }}
    >
      {restored ? (
        <Callout tone="info" className="mb-5" title="Unsent answers restored">
          You left this page without saving. The answers below were recovered
          from this device — check them, then save.
        </Callout>
      ) : null}

      {blockedOffline ? (
        <Callout tone="warning" className="mb-5" title="No connection">
          Your answers are saved on this phone. Move to somewhere with signal
          and press save again — nothing has been lost.
        </Callout>
      ) : null}

      {children}

      <DraftStatus online={online} savedAt={savedAt} />
    </form>
  );
}

function DraftStatus({
  online,
  savedAt,
}: {
  online: boolean;
  savedAt: number | null;
}) {
  if (!online) {
    return (
      <p className="mt-3 flex items-center gap-1.5 text-[12.5px] font-medium text-gold-700">
        <WifiOff className="h-3.5 w-3.5" aria-hidden />
        Offline — your answers are held on this device
      </p>
    );
  }
  if (savedAt === null) return null;
  return (
    <p
      className="mt-3 flex items-center gap-1.5 text-[12.5px] text-muted"
      aria-live="polite"
    >
      <HardDriveDownload className="h-3.5 w-3.5" aria-hidden />
      Draft kept on this device at{" "}
      {new Date(savedAt).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
      })}
    </p>
  );
}

/** Serialise a form, skipping files. Repeated names collapse to an array. */
function readForm(form: HTMLFormElement): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {};
  for (const [name, value] of new FormData(form).entries()) {
    if (typeof value !== "string") continue;
    const existing = out[name];
    if (existing === undefined) out[name] = value;
    else if (Array.isArray(existing)) existing.push(value);
    else out[name] = [existing, value];
  }
  return out;
}

function applyDraft(
  form: HTMLFormElement,
  values: Record<string, string | string[]>,
) {
  for (const [name, value] of Object.entries(values)) {
    const list = Array.isArray(value) ? value : [value];
    const wanted = new Set(list);
    const elements = [
      ...form.querySelectorAll<
        HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >(`[name="${CSS.escape(name)}"]`),
    ];

    // Repeated text fields — the subject/mark rows — are positional: the nth
    // saved value belongs to the nth element, not to all of them.
    let position = 0;
    for (const el of elements) {
      if (el instanceof HTMLInputElement) {
        if (el.type === "file") continue;
        if (el.type === "checkbox" || el.type === "radio") {
          setChecked(el, wanted.has(el.value));
          continue;
        }
      }
      setValue(el, list[position] ?? "");
      position += 1;
    }
  }
}

/**
 * Write a value in a way React notices.
 *
 * React patches the `value` property with a change tracker, so assigning
 * `el.value` directly updates the tracker too and the synthetic change event
 * is then treated as a no-op — leaving a controlled input showing restored
 * text that React does not know about, and reverting it on the next render.
 * Going through the prototype's own setter bypasses the patch, so the
 * dispatched event reaches onChange and component state catches up.
 */
function setValue(
  el: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement,
  value: string,
) {
  const proto =
    el instanceof HTMLInputElement
      ? HTMLInputElement.prototype
      : el instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLTextAreaElement.prototype;

  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, value);
  else el.value = value;

  // React maps onChange to `input` for text controls and `change` for selects.
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function setChecked(el: HTMLInputElement, checked: boolean) {
  if (el.checked === checked) return;
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "checked",
  )?.set;
  if (setter) setter.call(el, checked);
  else el.checked = checked;

  el.dispatchEvent(new Event("click", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

/** Banner for pages that are read-only when offline. */
export function OfflineBanner() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const sync = () => setOnline(navigator.onLine);
    sync();
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, []);

  if (online) return null;
  return (
    <div className="flex items-center gap-2 border-b border-gold-200 bg-gold-100 px-4 py-2 text-[12.5px] font-medium text-gold-700">
      <CloudOff className="h-4 w-4 shrink-0" aria-hidden />
      You are offline. This page is showing the last information that loaded.
    </div>
  );
}
