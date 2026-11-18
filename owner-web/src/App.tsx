import styles from "./App.module.css";

/** The owner web's first page. The owner screens of the Android app come in later tasks. */
export default function App() {
  return (
    <main className={styles.page}>
      <h1 className={styles.title}>BottleMap 사장님</h1>
      <p className={styles.message}>바 관리 기능을 준비하고 있어요.</p>
    </main>
  );
}
