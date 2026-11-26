import styles from "./PrivacyPolicyLink.module.css";

/**
 * The privacy policy, a static page the API serves at /privacy on this origin (backend/app/privacy). A plain link,
 * not a router link: the page is outside the owner web's /owner/ base.
 */
export const PRIVACY_POLICY_PATH = "/privacy";

export function PrivacyPolicyLink() {
  return (
    <a className={styles.link} href={PRIVACY_POLICY_PATH} target="_blank" rel="noopener noreferrer">
      개인정보처리방침
    </a>
  );
}

/** The footer of every signed-in screen. */
export function PrivacyFooter() {
  return (
    <footer className={styles.footer}>
      <PrivacyPolicyLink />
    </footer>
  );
}
