import Link from "next/link";
import { Foot, TopBar } from "@/components/TopBar";

export default function NotFound() {
  return (
    <main className="shell">
      <TopBar />
      <div className="section card empty">
        <h2>Nothing here</h2>
        <p className="sub">
          That optimization, option or run does not exist. <Link href="/">Back to the latest results</Link>.
        </p>
      </div>
      <Foot />
    </main>
  );
}
