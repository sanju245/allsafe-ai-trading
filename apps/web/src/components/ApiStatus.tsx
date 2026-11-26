"use client";

import { useApiHealth } from "./useApiHealth";

export default function ApiStatus() {
  const { status } = useApiHealth();
  if (status === "checking") {
    return <p className="as-pill" role="status">Checking account service…</p>;
  }
  if (status === "unavailable") {
    return (
      <p className="as-pill as-pill--amber">Account service unavailable</p>
    );
  }

  return (
    <p className="as-pill as-pill--green"><span className="as-led" aria-hidden="true" /> Account service online</p>
  );
}
