import { useEffect, useId, useRef, type ReactNode } from "react";
import styles from "./BottomSheet.module.css";

interface BottomSheetProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

/**
 * A modal sheet from the bottom of the screen (android/.../ui/common/OwnerBottomConfirmSheet.kt); centred on
 * wide screens. The native <dialog> keeps focus inside, closes on Escape, and makes the page behind inert.
 */
export function BottomSheet({ open, title, onClose, children }: BottomSheetProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // jsdom has no showModal; the attribute keeps the sheet visible there.
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={styles.sheet}
      aria-labelledby={titleId}
      onCancel={(event) => {
        // Escape: let the owner of `open` decide, so state and the dialog never disagree.
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the dialog itself, outside its content.
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className={styles.content}>
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        {children}
      </div>
    </dialog>
  );
}
