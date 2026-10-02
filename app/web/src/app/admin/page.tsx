export const dynamic = "force-dynamic";

// Operator page, English only (not a visitor screen).
export default function Page() {
  return (
    <main>
      <form method="post" action="/admin/session">
        <label>
          Admin token <input type="password" name="token" autoComplete="off" required />
        </label>
        <button type="submit">Open</button>
      </form>
    </main>
  );
}
