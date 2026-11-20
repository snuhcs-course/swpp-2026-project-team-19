import { useLayoutEffect, useRef, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { useMe } from "../owner/queries";
import { AppShell } from "../ui/AppShell";
import { Button } from "../ui/Button";
import { TextField } from "../ui/TextField";
import { useApplication } from "./ApplicationProvider";
import { caretAfterDigits, editDigits } from "./formattedInput";
import { formatOwnerPhone, phoneDigits } from "./rules";
import { STAGE_TITLES, stageOf, stepsBefore, type StepId } from "./steps";
import styles from "./application.module.css";

interface StepFrameProps {
  step: StepId;
  children: ReactNode;
  /** The button at the bottom (the app's RegistrationButton). */
  action?: { label: string; enabled: boolean; busy?: boolean; onClick: () => void };
  centered?: boolean;
}

/** One application screen: back, the 1-4 progress, its content, and its main button. */
export function StepFrame({ step, children, action, centered = false }: StepFrameProps) {
  const { draft, notices } = useApplication();
  const me = useMe();
  const navigate = useNavigate();
  const location = useLocation();
  const stage = stageOf(step);
  // Back follows the browser history inside the app; a resumed step goes to the one before it on the path.
  const previous = stepsBefore(step, draft.kind).at(-1);
  const canGoBack = location.key !== "default" || previous !== undefined;
  const back = () => (location.key !== "default" ? void navigate(-1) : void navigate(`/apply/${previous}`, { replace: true }));
  const notice = notices[step];

  return (
    <AppShell title="매장 등록" onBack={canGoBack && step !== "done" ? back : undefined} account={me.data?.email ?? null}>
      {stage > 0 ? (
        <div className={styles.progress} aria-label={`${stage}/4 ${STAGE_TITLES[stage - 1]}`}>
          <span className={styles.progressText}>
            {stage}/4 {STAGE_TITLES[stage - 1]}
          </span>
          <span className={styles.progressBar}>
            <span className={styles.progressFill} style={{ width: `${stage * 25}%` }} />
          </span>
        </div>
      ) : null}
      <div className={centered ? styles.centered : styles.content}>
        {notice ? (
          <p className={styles.notice} role="alert">
            {notice}
          </p>
        ) : null}
        {children}
      </div>
      {action ? (
        <div className={styles.action}>
          <Button disabled={!action.enabled} busy={action.busy} onClick={action.onClick}>
            {action.label}
          </Button>
        </div>
      ) : null}
    </AppShell>
  );
}

/** A screen's question and its explanation (OwnerV4Question). Line breaks in the title are kept. */
export function Question({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className={styles.question}>
      <h2 className={styles.questionTitle}>{title}</h2>
      {subtitle ? <p className={styles.questionText}>{subtitle}</p> : null}
    </header>
  );
}

export function Hint({ children }: { children: ReactNode }) {
  return <p className={styles.hint}>{children}</p>;
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p className={styles.error} role="alert">
      {children}
    </p>
  );
}

/** A labelled value with an edit link (OwnerV4Summary, OwnerV4Previous, RegistrationPartialRow). */
export function SummaryRow({ label, value, actionLabel = "수정", onEdit }: { label: string; value: string; actionLabel?: string; onEdit?: () => void }) {
  return (
    <div className={styles.row}>
      <span className={styles.rowLabel}>{label}</span>
      <span className={styles.rowValue}>{value}</span>
      {onEdit ? (
        <button type="button" className={styles.rowAction} onClick={onEdit} aria-label={`${label} ${actionLabel}`}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

/** A centred status (RegistrationCenterContent): reading, checking, results, done. */
export function CenterContent({ title, text, loading = false }: { title: string; text?: string; loading?: boolean }) {
  return (
    <div className={styles.center} role={loading ? "status" : undefined} aria-busy={loading || undefined}>
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : null}
      <h2 className={styles.questionTitle}>{title}</h2>
      {text ? <p className={styles.questionText}>{text}</p> : null}
    </div>
  );
}

/** Who sees a value (RegistrationVisibility): customers, or only the operators. */
export function Visibility({ isPublic }: { isPublic: boolean }) {
  return <span className={isPublic ? styles.badgePublic : styles.badge}>{isPublic ? "손님에게 보여요" : "운영팀만 봐요"}</span>;
}

interface DigitsFieldProps {
  label: string;
  digits: string;
  maxDigits: number;
  format: (digits: string) => string;
  onDigits: (digits: string) => void;
  placeholder?: string;
  hint?: string;
  error?: string;
  inputMode?: "numeric" | "tel";
}

/** A number typed as digits and shown with separators; the caret stays where the owner is typing. */
export function DigitsField({ label, digits, maxDigits, format, onDigits, inputMode = "numeric", ...rest }: DigitsFieldProps) {
  const input = useRef<HTMLInputElement>(null);
  const caret = useRef<number | null>(null);
  const text = format(digits);

  useLayoutEffect(() => {
    const element = input.current;
    if (caret.current === null || !element || document.activeElement !== element) return;
    const position = caretAfterDigits(text, caret.current);
    element.setSelectionRange(position, position);
    caret.current = null;
  }, [text]);

  return (
    <TextField
      {...rest}
      ref={input}
      label={label}
      value={text}
      inputMode={inputMode}
      autoComplete="off"
      onChange={(event) => {
        const target = event.currentTarget;
        const edit = editDigits(digits, text, target.value, target.selectionStart ?? target.value.length, maxDigits);
        caret.current = edit.caretDigits;
        onDigits(edit.digits);
      }}
    />
  );
}

export function PhoneField(props: { label: string; digits: string; onDigits: (digits: string) => void; hint?: string; error?: string }) {
  return <DigitsField {...props} maxDigits={12} format={(digits) => formatOwnerPhone(phoneDigits(digits))} inputMode="tel" placeholder="010-0000-0000" />;
}
