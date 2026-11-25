type WorkspaceIconName = "dashboard" | "chart" | "account" | "request" | "shield";

const icons: Record<WorkspaceIconName, string> = {
  dashboard: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  chart: "M3 3v17h18M7 15l4-4 3 2 6-7",
  account: "M20 21H4v-2a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5zM16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z",
  request: "M8 7h8M8 11h8M8 15h4M5 3h14v18H5z",
  shield: "M12 22c5-2 8-5 8-9V5l-8-3-8 3v8c0 4 3 7 8 9zM9 12l2 2 4-4",
};

export default function WorkspaceIcon({ name }: { name: WorkspaceIconName }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <path d={icons[name]} />
    </svg>
  );
}
