import Link from "next/link";

export const metadata = { title: "Privacy · AllSafe AI Trading" };

export default function PrivacyPage() {
  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-10 text-slate-300 sm:px-6">
      <Link href="/" className="text-sm font-semibold text-white">AllSafe <span className="text-emerald-400">AI Trading</span></Link>
      <h1 className="mt-8 text-3xl font-bold text-white">Privacy Policy</h1>
      <div className="mt-6 space-y-5 text-sm leading-7">
        <p>When you request an account, we collect your name, date of birth, email address, phone number, WhatsApp number, and the source IP observed by the account service. The server uses that address for abuse limiting and request auditing. We store your request, its submission time, and the administrator&apos;s decision in Supabase so an administrator can review it.</p>
        <p>We use your email address to verify new applications and send a receipt and decision. The account administrator receives the application details to review the request. A protected password hash is held separately while the request is pending. Approval creates a Supabase Authentication account that uses the chosen password.</p>
        <p>The API checks your sign-in token, account role, and account status when you sign in or use protected features. Customer access is not restricted to a specific IP address. Only authorized administrators and the server-side service credential can access request details. The web browser does not receive the service credential.</p>
        <p>To help the administrator review account activity and investigate possible sharing, we keep the time and network IP address for up to ten successful sign-ins per customer. This history is visible in the administrator portal. Older entries are removed as you sign in again, and deleting the customer account removes its history.</p>
        <p>We store account warnings and the current pause reason when the administrator adds them. A customer can see their own warnings in AllSafe and their pause reason after verifying their identity. Resuming the account removes its pause reason.</p>
        <p>Administrators can remove application records from the request queue. Deleting a customer login also removes the linked application. You may ask the administrator to correct or remove your information, or to pause or delete account access. Hosting, authentication, and email providers may retain operational records under their own policies.</p>
      </div>
      <Link href="/" className="mt-8 inline-block text-sm font-medium text-emerald-300 underline">Back to home</Link>
    </main>
  );
}
