import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import type { PreparedImage } from "../images/prepare";
import { useMe } from "../owner/queries";
import { clearDraft, emptyDraft, loadDraft, saveDraft, type ApplicationDraft } from "./draft";
import { pickedPhoto } from "./photos";
import type { StepId } from "./steps";

/** A photo picked on this visit, with a preview URL for its thumbnail. */
export interface PickedPhoto {
  id: string;
  image: PreparedImage;
  previewUrl: string;
}

interface Application {
  draft: ApplicationDraft;
  /** Always the latest draft, for async work that must compare against what is on screen now. */
  latest: () => ApplicationDraft;
  update: (change: Partial<ApplicationDraft> | ((draft: ApplicationDraft) => ApplicationDraft)) => void;
  cover: PickedPhoto | null;
  /** Picks the cover photo. A new one is sent again on the next submission, even if an earlier one was. */
  setCover: (image: PreparedImage | null) => void;
  menus: PickedPhoto[];
  setMenus: (change: (menus: PickedPhoto[]) => PickedPhoto[]) => void;
  /** A message to show on a step the owner is sent back to (e.g. by a refused submission). */
  notices: Partial<Record<StepId, string>>;
  setNotice: (step: StepId, message: string | null) => void;
  /** Whether the current step was opened from review ("수정"), so finishing it returns there. */
  editingReview: boolean;
  go: (step: StepId, options?: { replace?: boolean; fromReview?: boolean }) => void;
  /** The next step, or back to review when editing from it (forward() in OwnerOnboardingScreen.kt). */
  forward: (step: StepId) => void;
  /** Ends the application on this browser: drops the draft and the photos. */
  finish: () => void;
  /** Whether the owner is on `step` now (for async work that finishes after they may have moved on). */
  isAt: (step: StepId) => boolean;
  /** Whether a business certificate is being read, so the reading screen has something to wait for. */
  reading: boolean;
  /** Starts reading a certificate and returns its run, which finishReading takes back. */
  startReading: () => number;
  /**
   * Ends a run. True only if it is the latest run and the owner is still waiting on the reading screen:
   * a result that comes after they left (or picked another photo) must not overwrite what they typed.
   */
  finishReading: (run: number) => boolean;
  /** The application exists on the server (its photos are still to be sent): only the photos can change. */
  locked: boolean;
}

const ApplicationContext = createContext<Application | null>(null);

/** The application in progress: the saved draft, the photos of this visit, and moving between steps. */
export function ApplicationProvider({ children }: { children: ReactNode }) {
  const userId = useMe().data?.userId ?? "";
  const navigate = useNavigate();
  const location = useLocation();
  const [draft, setDraft] = useState<ApplicationDraft>(() => loadDraft(userId) ?? emptyDraft());
  const latestDraft = useRef(draft);
  const [cover, setCoverState] = useState<PickedPhoto | null>(null);
  const [menus, setMenusState] = useState<PickedPhoto[]>([]);
  const [notices, setNotices] = useState<Partial<Record<StepId, string>>>({});
  const [reading, setReading] = useState(false);
  const readingRun = useRef(0);
  const finished = useRef(false);
  const path = useRef(location.pathname);
  const fromStep = useRef(false);
  useEffect(() => {
    path.current = location.pathname;
    fromStep.current = (location.state as { fromStep?: boolean } | null)?.fromStep === true;
  }, [location.pathname, location.state]);

  const update = useCallback(
    (change: Partial<ApplicationDraft> | ((current: ApplicationDraft) => ApplicationDraft)) => {
      const next = typeof change === "function" ? change(latestDraft.current) : { ...latestDraft.current, ...change };
      latestDraft.current = next;
      setDraft(next);
      if (!finished.current && userId) saveDraft(userId, next);
    },
    [userId],
  );

  const setCover = useCallback(
    (image: PreparedImage | null) => {
      setCoverState((previous) => {
        if (previous) URL.revokeObjectURL(previous.previewUrl);
        return image ? pickedPhoto(image) : null;
      });
      // The server keeps the photo sent before; the replacement has to be sent too (PUT replaces it).
      if (image && latestDraft.current.uploaded.cover) update((current) => ({ ...current, uploaded: { ...current.uploaded, cover: false } }));
    },
    [update],
  );

  const setMenus = useCallback((change: (current: PickedPhoto[]) => PickedPhoto[]) => {
    setMenusState((previous) => {
      const next = change(previous);
      for (const photo of previous) if (!next.includes(photo)) URL.revokeObjectURL(photo.previewUrl);
      return next;
    });
  }, []);

  const setNotice = useCallback((step: StepId, message: string | null) => {
    setNotices((current) => ({ ...current, [step]: message ?? undefined }));
  }, []);

  const editingReview = (location.state as { fromReview?: boolean } | null)?.fromReview === true;

  const go = useCallback(
    (step: StepId, options: { replace?: boolean; fromReview?: boolean } = {}) => {
      if (step !== "reading" && step !== "done") update({ step });
      // fromStep: the entry before this one is a step of the form, so Back can be the browser's own. A
      // replacement keeps the entry before the current one, and so its fromStep.
      const state = { fromStep: options.replace ? fromStep.current : true, fromReview: options.fromReview === true };
      void navigate(`/apply/${step}`, { replace: options.replace, state });
    },
    [navigate, update],
  );

  const forward = useCallback((step: StepId) => go(editingReview ? "review" : step), [go, editingReview]);

  const startReading = useCallback(() => {
    readingRun.current += 1;
    setReading(true);
    return readingRun.current;
  }, []);

  const finishReading = useCallback((run: number) => {
    if (run !== readingRun.current) return false;
    setReading(false);
    return path.current === "/apply/reading";
  }, []);

  const finish = useCallback(() => {
    finished.current = true;
    if (userId) clearDraft(userId);
    setCover(null);
    setMenus(() => []);
  }, [userId, setCover, setMenus]);

  // Photos are released with the page.
  const photos = useRef({ cover, menus });
  useEffect(() => {
    photos.current = { cover, menus };
  }, [cover, menus]);
  useEffect(
    () => () => {
      if (photos.current.cover) URL.revokeObjectURL(photos.current.cover.previewUrl);
      for (const photo of photos.current.menus) URL.revokeObjectURL(photo.previewUrl);
    },
    [],
  );

  const value = useMemo<Application>(
    () => ({
      draft,
      latest: () => latestDraft.current,
      update,
      cover,
      setCover,
      menus,
      setMenus,
      notices,
      setNotice,
      editingReview,
      go,
      forward,
      finish,
      isAt: (step: StepId) => path.current === `/apply/${step}`,
      reading,
      startReading,
      finishReading,
      locked: draft.applicationId !== null,
    }),
    [draft, update, cover, setCover, menus, setMenus, notices, setNotice, editingReview, go, forward, finish, reading, startReading, finishReading],
  );
  return <ApplicationContext.Provider value={value}>{children}</ApplicationContext.Provider>;
}

export function useApplication(): Application {
  const application = useContext(ApplicationContext);
  if (!application) throw new Error("useApplication must be used inside ApplicationProvider.");
  return application;
}

