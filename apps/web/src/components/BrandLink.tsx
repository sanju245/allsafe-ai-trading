import Link from "next/link";

export default function BrandLink() {
  return (
    <Link href="/" aria-label="AllSafe AI Trading home" className="as-brand">
      <span className="as-brand-mark" aria-hidden="true"><i /><i /><i /></span>
      <span className="as-brand-name">AllSafe <span>AI Trading</span></span>
    </Link>
  );
}
