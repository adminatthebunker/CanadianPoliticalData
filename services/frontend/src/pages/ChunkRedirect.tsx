import { useEffect, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { fetchJson } from "../api";

type ChunkLookup = { speech_id: string; chunk_index: number };

export default function ChunkRedirect() {
  const { id } = useParams<{ id: string }>();
  const [target, setTarget] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    fetchJson<ChunkLookup>(`/chunks/${id}`)
      .then((row) => {
        if (cancelled) return;
        setTarget(`/speeches/${row.speech_id}#chunk-${id}`);
      })
      .catch(() => {
        if (cancelled) return;
        setNotFound(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (notFound) return <Navigate to="/search" replace />;
  if (target) return <Navigate to={target} replace />;

  return (
    <div style={{ padding: "2rem", textAlign: "center", color: "#888" }}>
      Loading chunk…
    </div>
  );
}
