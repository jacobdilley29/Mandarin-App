import { useNavigate } from "react-router-dom";
import { type TutorFocus } from "../api";

// "Ask about this" — the contextual entry point to the tutor (spec §3.7).
//
// §3.7 asks that the tutor be "given context about what Jacob is currently
// working on ... so answers reference the actual curriculum rather than being
// generic". A question usually occurs to you mid-lesson, looking at the thing
// that confused you; retyping it into a blank chat is where that context gets
// lost. This carries the item across instead.
//
// Handed over in sessionStorage rather than a query string: a sentence or a
// grammar explanation doesn't belong in a URL, and the handoff is single-use.
export function AskAbout({ focus, label = "Ask about this" }: { focus: TutorFocus; label?: string }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => {
        try {
          sessionStorage.setItem("tutor:focus", JSON.stringify(focus));
        } catch {
          // Private windows can refuse storage; the tutor still opens, just
          // without the item pre-loaded.
        }
        navigate("/talk");
      }}
      className="tap inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs text-ink-soft hover:border-primary hover:text-ink"
    >
      <span aria-hidden>💬</span>
      {label}
    </button>
  );
}
