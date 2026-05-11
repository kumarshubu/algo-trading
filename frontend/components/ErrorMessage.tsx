export default function ErrorMessage({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg p-4 text-sm"
      style={{ background: "#2d1515", border: "1px solid #7f1d1d", color: "#fca5a5" }}
    >
      {message}
    </div>
  );
}
