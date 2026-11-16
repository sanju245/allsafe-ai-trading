import Link from "next/link";

export const metadata = { title: "Privacy · AllSafe AI Trading" };

export default function PrivacyPage() {
  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-10 text-slate-300 sm:px-6">
      <Link href="/" className="text-sm font-semibold text-white">AllSafe <span className="text-emerald-400">AI Trading</span></Link>
      <h1 className="mt-8 text-3xl font-bold text-white">Privacy Policy</h1>
      <div className="mt-6 space-y-5 text-sm leading-7">
        <p>When you request an account, we collect your name, date of birth, email address, phone number, WhatsApp number, and public IP address. The API checks your IP against the address it observes. We store your request, its submission time, and the administrator&apos;s decision in Supabase so an administrator can review it.</p>
        <p>We use your email address to send a request receipt and an approval or decline notice through the configured email provider. An approved request creates a Supabase Authentication account. Your password is set through a one-time link; we do not ask you to email it to the administrator.</p>
        <p>Customer access is restricted to an approved public IP. The API checks your account role, status, and current IP when you sign in or use protected features. Only authorized administrators and the server-side service credential can access request details. The web browser does not receive the service credential.</p>
        <p>Request records, including declined requests, remain in the database until an administrator removes them. You may ask the administrator to correct or remove your information, or to pause or delete account access. Hosting, authentication, and email providers may retain operational records under their own policies.</p>
      </div>
      <Link href="/" className="mt-8 inline-block text-sm font-medium text-emerald-300 underline">Back to home</Link>
    </main>
  );
}
