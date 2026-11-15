# Transfer the administrator account

The owner requested the active administrator identity `Sanjay200123@gmail.com` on 2026-11-15. This is an operational role transfer, not an application email bypass. The API must continue authorizing the current role from `public.profiles` after token verification.

The manager observed these two existing active profiles in the live database:

| Identity | User ID | Before role | Requested role |
|---|---|---|---|
| sanjay200123@gmail.com | 2997e4f7-1b53-4d75-b081-aaf3296e52f4 | user | admin |
| sanjay@gmail.com | e557a06c-956f-4fff-85a1-a6c7b3d0dbf0 | admin | user |

## Reviewed transaction

Run `preflight.sql` first through an authorized Supabase session. It lists only the two profiles and whether each profile matches its Auth email. It also reports the current admin count and whether the single-admin index exists. Preserve the result as a restricted operational record.

`transfer.sql` locks the profile table for the short transaction and validates both exact user IDs, their case-insensitive profile/Auth email match, active status, and the sole current admin. It demotes the prior admin before promoting the requested admin, satisfying the single-admin unique index. All changes commit together. Any unexpected state aborts the transaction. If the requested transfer already completed, the script makes no changes.

The transaction clears the new administrator's allowed_ip to NULL and preserves passwords, Auth email, account status, provider configuration, and trading behavior. The preflight snapshot showed the target's prior customer IP as 152.58.183.233; the transfer aborts if that customer address changed before execution. The former admin becomes an ordinary user and retains their existing customer IP rule. Review that address before expecting customer access from a different network.

Only the manager may execute this operation after verifying the live account state and the user's authorization. The specialist prepared and reviewed these scripts but did not execute them.

## Verification and rollback

After commit, rerun `preflight.sql`. Exactly one administrator must remain, matching the requested identity. Independently sign in through /admin/login and check that the API returns role=admin from more than one IP or a controlled test. A live login still requires the account's existing credentials; the role transfer does not set or reveal a password.

`rollback.sql` is a guarded, atomic reversal limited to these same two profiles. It validates that the requested account is the sole active admin with NULL allowed_ip and the former account is still an active ordinary user, then reverses their roles and restores the target's prior customer address, 152.58.183.233. It preserves all other account data and aborts if the state has changed. Do not run rollback as a routine follow-up.
