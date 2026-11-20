import { Navigate, Outlet, useParams } from "react-router";
import { ApplicationProvider, useApplication } from "./ApplicationProvider";
import { AddressStep, BarNameStep, BarPhoneStep, ContactStep, CoverStep, DoneStep, MenusStep, ReviewStep } from "./barSteps";
import {
  CheckStep,
  IntroStep,
  MethodStep,
  NumberStep,
  OpeningDateStep,
  ReadingStep,
  RepresentativeStep,
  ResultStep,
} from "./businessSteps";
import { businessVerificationIsCurrent } from "./rules";
import { isStepId, type StepId } from "./steps";

/** /apply/*: the owner application (P11), with its draft and photos shared by every step. */
export function ApplicationLayout() {
  return (
    <ApplicationProvider>
      <Outlet />
    </ApplicationProvider>
  );
}

/** /apply: continues a saved application where it stopped, or starts one. */
export function ApplicationResume() {
  const { draft } = useApplication();
  return <Navigate to={`/apply/${draft.step}`} replace />;
}

const SCREENS: Record<StepId, () => React.ReactNode> = {
  intro: IntroStep,
  method: MethodStep,
  reading: ReadingStep,
  number: NumberStep,
  representative: RepresentativeStep,
  "opening-date": OpeningDateStep,
  check: CheckStep,
  result: ResultStep,
  "bar-name": BarNameStep,
  cover: CoverStep,
  address: AddressStep,
  "bar-phone": BarPhoneStep,
  menus: MenusStep,
  contact: ContactStep,
  review: ReviewStep,
  done: DoneStep,
};

/** /apply/:step, with the app's rules for steps that need something first (OwnerOnboardingScreen.kt). */
export function ApplicationStep() {
  const { step } = useParams();
  const { draft, reading } = useApplication();
  if (!isStepId(step)) return <Navigate to="/apply" replace />;

  // Nothing is being read (e.g. after a reload): go on to check the fields.
  if (step === "reading" && !reading) return <Navigate to="/apply/check" replace />;
  // A result, and the review, only stand for the values on screen now; edited values are checked again.
  // (Which results allow sending is the review's own rule: its button stays off for the others.)
  const current = businessVerificationIsCurrent(draft.verification?.key, draft);
  if ((step === "result" || step === "review") && !current) return <Navigate to="/apply/check" replace />;

  const Screen = SCREENS[step];
  return <Screen />;
}
