import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import mermaid from "mermaid";
import api from "../api/client";

import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Info,
  Check,
  Leaf,
} from "lucide-react";

const C = {
  forest: "#1F3D2B",
  forest2: "#2F6B3E",
  cream: "#F2EBDD",
  paper: "#FAF8F1",
  brass: "#C97A2B",
  brassSoft: "#F4E8CB",
  line: "#D8D0BA",
  ink: "#26312A",
  muted: "#817A63",
  muted2: "#9C9679",
  danger: "#7A2E2E",
  dangerSoft: "#F6E8E6",
};

const STATUS_COLORS = {
  VERIFIED: C.forest2,
  PASSED: C.forest2,
  PARTIAL: "#B4893D",
  ABSTAINED: C.danger,
  FAILED: C.danger,
  INSUFFICIENT: C.danger,
  PENDING: "#A5A092",
  SKIPPED: "#A5A092",
  UNAVAILABLE: "#8E8A7D",
};

const GRAPH_WIDTH = 600;
const GRAPH_MIN_HEIGHT = 400;

function EvalDashboard() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const qParam = searchParams.get("q");

  const [allQueries, setAllQueries] = useState([]);
  const [selectedQueryIndex, setSelectedQueryIndex] = useState(0);

  const [graphSvg, setGraphSvg] = useState("");

  const [loading, setLoading] = useState(true);

  const [selectedNode, setSelectedNode] = useState(null);

  const [inspectorHeight, setInspectorHeight] = useState(280);
  const [resizingInspector, setResizingInspector] = useState(false);
  const graphRef = useRef(null);

  const graphScrollRef = useRef(null);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: "base",

      themeVariables: {
        primaryColor: C.paper,
        primaryBorderColor: C.forest2,
        primaryTextColor: C.ink,
        lineColor: "#59635B",
        fontFamily: "IBM Plex Sans",
        fontSize: "13px",

        secondaryColor: C.cream,
        tertiaryColor: "#E8F0E9",

        clusterBkg: "#F7F4EB",
        clusterBorder: C.line,

        edgeLabelBackground: C.paper,
      },

      flowchart: {
        htmlLabels: true,
        useMaxWidth: false,
        nodeSpacing: 22,
        rankSpacing: 30,
        diagramPadding: 8,
        padding: 5,
        curve: "basis",
      },
    });

    window.handleNodeClick = (nodeId) => {
      setSelectedNode(nodeId);
    };

    return () => {
      delete window.handleNodeClick;
    };
  }, []);

  /*
   * Resizable inspector.
   * Drag the little handle upward to make the inspector taller.
   */
  useEffect(() => {
    if (!resizingInspector) return;

    const move = (event) => {
      const nextHeight = window.innerHeight - event.clientY;

      const minHeight = 190;
      const maxHeight = Math.floor(window.innerHeight * 0.72);

      setInspectorHeight(
        Math.max(minHeight, Math.min(maxHeight, nextHeight))
      );
    };

    const stop = () => {
      setResizingInspector(false);
    };

    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", stop);

    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", stop);
    };
  }, [resizingInspector]);

  /*
   * Fetch evaluation data.
   * Kept compatible with your existing backend.
   */
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);

        const [, metricsRes] = await Promise.all([
          api.get("/api/eval/graph"),
          api.get(`/api/eval/metrics/${sessionId}`),
        ]);

        const queries = metricsRes?.queries || [];

        setAllQueries(queries);

        if (queries.length > 0) {
          if (
            qParam !== null &&
            !Number.isNaN(Number(qParam)) &&
            Number(qParam) >= 0 &&
            Number(qParam) < queries.length
          ) {
            setSelectedQueryIndex(Number(qParam));
          } else {
            setSelectedQueryIndex(queries.length - 1);
          }
        } else {
          setSelectedQueryIndex(0);
        }
      } catch (error) {
        console.error("Error fetching eval data:", error);
        setAllQueries([]);
      } finally {
        setLoading(false);
      }
    };

    if (sessionId) {
      fetchData();
    }
  }, [sessionId, qParam]);

  /*
   * Rebuild the Mermaid source whenever the selected query changes.
   */
  useEffect(() => {
    if (!allQueries.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setGraphSvg("");
      return;
    }

    const buildGraph = async () => {
      try {
        const graphRes = await api.get("/api/eval/graph");

        let graph = graphRes?.graph || "";
        const metrics = allQueries[selectedQueryIndex];

        if (!graph) {
          setGraphSvg("");
          return;
        }

        /*
         * Remove Mermaid frontmatter if backend returns:
         * ---
         * ...
         * ---
         */
        graph = graph.trim();

        if (graph.startsWith("---")) {
          const endIdx = graph.indexOf("---", 3);

          if (endIdx !== -1) {
            graph = graph.substring(endIdx + 3).trim();
          }
        }

        /*
         * Keep the diagram compact.
         * This is intentionally NOT using useMaxWidth:true.
         */
        const directives = `
%%{
  init: {
    "theme": "base",
    "themeVariables": {
      "primaryColor": "${C.paper}",
      "primaryBorderColor": "${C.forest2}",
      "primaryTextColor": "${C.ink}",
      "lineColor": "#59635B",
      "fontFamily": "IBM Plex Sans",
      "fontSize": "13px"
    },
    "flowchart": {
      "htmlLabels": true,
      "useMaxWidth": false,
      "nodeSpacing": 22,
      "rankSpacing": 30,
      "diagramPadding": 8,
      "padding": 5,
      "curve": "basis"
    }
  }
}%%
`;

        const styles = [];

        Object.entries(metrics?.nodes || {}).forEach(
          ([node, nodeData]) => {
            const color =
              STATUS_COLORS[nodeData.status] ||
              STATUS_COLORS.UNAVAILABLE;

            styles.push(
              `style ${node} fill:${color},color:#FAF8F1,stroke:#26312A,stroke-width:1px`
            );
          }
        );

        const modifiedGraph =
          directives +
          graph +
          "\n" +
          styles.join("\n");

        /*
         * IMPORTANT:
         * Render the SVG ourselves instead of mermaid.contentLoaded().
         * This prevents Mermaid from deciding its own responsive width.
         */
        const renderId = `eval-graph-${Date.now()}`;

        const { svg } = await mermaid.render(
          renderId,
          modifiedGraph
        );

        setGraphSvg(svg);
      } catch (error) {
        console.error("Failed to render evaluation graph:", error);
        setGraphSvg("");
      }
    };

    buildGraph();
  }, [selectedQueryIndex, allQueries]);

  useEffect(() => {
    const container = graphRef.current;

    if (!container) return;

    const handleGraphClick = (event) => {
      const nodeElement = event.target.closest(".node");

      if (!nodeElement) return;

      const nodeId = nodeElement.getAttribute("id");

      if (!nodeId) return;

      /*
       * Mermaid normally generates ids like:
       *
       * flowchart-worker-0
       * flowchart-detect_intent-1
       *
       * We match that against the actual backend node names.
       */
      const nodeNames = Object.keys(
        allQueries[selectedQueryIndex]?.nodes || {}
      );

      // Sort by length descending so longer, more specific names match before shorter ones
      const sortedNodeNames = [...nodeNames].sort((a, b) => b.length - a.length);

      let matchedNode = sortedNodeNames.find((name) => {
        // Mermaid sometimes replaces underscores with dashes in IDs
        const nameDashed = name.replace(/_/g, "-");
        return nodeId.includes(name) || nodeId.includes(nameDashed);
      });

      /*
       * Fallback:
       * inspect the visible node text.
       */
      if (!matchedNode) {
        const visibleText =
          nodeElement.textContent
            ?.trim()
            .replace(/\s+/g, " ")
            .toLowerCase() || "";

        matchedNode = sortedNodeNames.find((name) => {
          const rawName = name.toLowerCase();
          const spacedName = name.replace(/_/g, " ").toLowerCase();

          return (
            visibleText === rawName ||
            visibleText.includes(rawName) ||
            visibleText === spacedName ||
            visibleText.includes(spacedName)
          );
        });
      }

      if (matchedNode) {
        setSelectedNode(matchedNode);
      }
    };

    container.addEventListener(
      "click",
      handleGraphClick
    );

    return () => {
      container.removeEventListener(
        "click",
        handleGraphClick
      );
    };
  }, [graphSvg, selectedQueryIndex, allQueries]);

  if (loading) {
    return (
      <div
        className="flex h-[100dvh] items-center justify-center"
        style={{
          background: C.cream,
          color: C.ink,
          fontFamily: "IBM Plex Sans, sans-serif",
        }}
      >
        <div className="flex flex-col items-center gap-4">
          <div
            className="h-7 w-7 animate-spin rounded-full border-2"
            style={{
              borderColor: C.line,
              borderTopColor: C.forest2,
            }}
          />

          <span
            className="text-[10px] font-semibold tracking-[.16em]"
            style={{ color: C.muted }}
          >
            LOADING EVALUATION
          </span>
        </div>
      </div>
    );
  }

  const metrics = allQueries[selectedQueryIndex] || {};

  const outcomeStatus =
    metrics.outcome?.status || "UNAVAILABLE";

  const isAbstained =
    typeof metrics.outcome?.is_abstained === "boolean"
      ? metrics.outcome.is_abstained
      : null;

  const tasks = metrics.tasks || [];

  const selectedStatus =
    metrics.nodes?.[selectedNode]?.status ||
    "UNAVAILABLE";

  const getStatusIcon = (status) => {
    if (["VERIFIED", "PASSED"].includes(status)) {
      return <CheckCircle2 size={16} />;
    }

    if (status === "PARTIAL") {
      return <AlertTriangle size={16} />;
    }

    if (
      ["FAILED", "INSUFFICIENT", "ABSTAINED"].includes(status)
    ) {
      return <XCircle size={16} />;
    }

    return <Clock size={16} />;
  };

  return (
    <div
      className="flex h-[100dvh] flex-col overflow-hidden"
      style={{
        background: C.cream,
        color: C.ink,
        fontFamily: "IBM Plex Sans, sans-serif",
      }}
    >
      {/* =====================================================
          LOCAL SCOPED STYLES

          These intentionally override the global .eval-mermaid CSS
          that was making Mermaid responsive.
      ===================================================== */}

      <style>{`
        .ipshakti-eval-graph {
          width: ${GRAPH_WIDTH}px !important;
          min-width: ${GRAPH_WIDTH}px !important;
          max-width: none !important;
          flex: 0 0 ${GRAPH_WIDTH}px !important;
        }

        .ipshakti-eval-graph svg {
          width: ${GRAPH_WIDTH}px !important;
          min-width: ${GRAPH_WIDTH}px !important;
          max-width: none !important;
          height: auto !important;
          display: block !important;
        }

        .ipshakti-eval-graph .nodeLabel,
        .ipshakti-eval-graph .edgeLabel {
          font-size: 13px !important;
        }

        .ipshakti-eval-graph .node rect,
        .ipshakti-eval-graph .node polygon,
        .ipshakti-eval-graph .node circle,
        .ipshakti-eval-graph .node ellipse {
          stroke-width: 1px !important;
        }

        .ipshakti-eval-graph .node {
          cursor: pointer !important;
          pointer-events: all !important;
        }

        .ipshakti-eval-graph foreignObject {
          overflow: visible !important;
        }
      `}</style>

      {/* =====================================================
          HEADER
      ===================================================== */}

      <header
        className="relative z-50 flex h-[82px] shrink-0 items-center justify-between border-b px-5 md:px-6"
        style={{
          borderColor: C.line,
          background: "rgba(250,248,241,.96)",
        }}
      >
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate("/")}
            className="flex h-9 w-9 items-center justify-center rounded-lg border bg-white transition hover:bg-[#F4E8CB]"
            style={{ borderColor: C.line }}
          >
            <ArrowLeft size={16} />
          </button>

          <div className="flex items-center gap-3">
            <div
              className="grid h-9 w-9 place-items-center rounded-full"
              style={{
                background: C.forest,
                color: C.paper,
              }}
            >
              <Leaf size={16} />
            </div>

            <div>
              <h1 className="font-['Newsreader'] text-xl font-semibold">
                Research quality cockpit
              </h1>

              <div
                className="mt-1 font-mono text-[9px]"
                style={{ color: C.muted }}
              >
                {sessionId}
              </div>
            </div>
          </div>
        </div>

        <div
          className="flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-semibold"
          style={{
            background: C.brassSoft,
            color: "#8A652B",
            borderColor: `${C.brass}40`,
          }}
        >
          <Info size={13} />
          INTERNAL EVALUATION
        </div>
      </header>

      {/* =====================================================
          BODY
      ===================================================== */}

      <div className="flex min-h-0 flex-1 overflow-hidden">

        {/* ===================================================
            LEFT QUERY LIST
        =================================================== */}

        <aside
          className="flex w-[300px] shrink-0 flex-col border-r"
          style={{
            borderColor: C.line,
            background: "#F7F4EB",
          }}
        >
          <div
            className="border-b px-4 py-4"
            style={{ borderColor: C.line }}
          >
            <div
              className="text-[9px] font-semibold tracking-[.16em]"
              style={{ color: C.muted }}
            >
              EVALUATION QUEUE
            </div>

            <div
              className="mt-1 text-[10px]"
              style={{ color: C.muted2 }}
            >
              {allQueries.length} captured queries
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            {allQueries.map((q, idx) => {
              const active = selectedQueryIndex === idx;

              return (
                <motion.button
                  key={idx}
                  whileTap={{ scale: 0.99 }}
                  onClick={() => {
                    setSelectedQueryIndex(idx);
                    setSelectedNode(null);
                  }}
                  className="mb-1 w-full rounded-xl border p-3 text-left transition"
                  style={{
                    borderColor: active
                      ? "#2F6B3E35"
                      : "transparent",
                    background: active
                      ? "#FFFFFF"
                      : "transparent",
                    boxShadow: active
                      ? "0 6px 18px rgba(38,49,42,.05)"
                      : "none",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span
                      className="text-[10px] font-semibold"
                      style={{
                        color: active
                          ? C.forest2
                          : C.muted,
                      }}
                    >
                      Q{String(idx + 1).padStart(2, "0")}
                    </span>

                    <span
                      className="font-mono text-[9px]"
                      style={{ color: C.muted2 }}
                    >
                      ID:{idx.toString().padStart(3, "0")}
                    </span>
                  </div>

                  <div
                    className="mt-2 line-clamp-3 text-xs leading-5"
                    style={{ color: "#6E6852" }}
                  >
                    {q.raw_query || "N/A"}
                  </div>
                </motion.button>
              );
            })}

            {allQueries.length === 0 && (
              <div
                className="m-2 rounded-xl border border-dashed p-5 text-center text-xs"
                style={{
                  borderColor: C.line,
                  color: C.muted,
                }}
              >
                No evaluation records found.
              </div>
            )}
          </div>
        </aside>

        {/* ===================================================
            MAIN
        =================================================== */}

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">

          {/* ================================================
              GRAPH VIEWPORT

              THIS is the only thing that scrolls.
          ================================================= */}

          <section
            className="relative min-h-0 flex-1 overflow-hidden"
            style={{
              background: C.paper,
            }}
          >
            <div
              ref={graphScrollRef}
              className="absolute inset-0 overflow-auto"
              style={{
                backgroundImage:
                  "radial-gradient(#DED7C6 1px, transparent 1px)",
                backgroundSize: "22px 22px",
              }}
            >

              {/* ===========================================
                  STICKY SCORE BAR
              ============================================ */}

              <div
                className="sticky top-0 z-40 px-4 pt-4 md:px-6"
                style={{
                  pointerEvents: "none",
                }}
              >
                <div
                  className="rounded-2xl border px-5 py-3 shadow-[0_8px_24px_rgba(38,49,42,.08)] backdrop-blur-xl"
                  style={{
                    borderColor: C.line,
                    background: "rgba(250,248,241,.96)",
                    pointerEvents: "auto",
                  }}
                >
                  <div className="flex items-center justify-between gap-6">

                    <div className="flex items-center gap-7">

                      <Score
                        label="Heuristic"
                        value={
                          metrics.scores
                            ?.confidence_heuristic ?? "-"
                        }
                      />

                      <Divider />

                      <Score
                        label="Coverage"
                        value={`${metrics.scores?.task_coverage ?? 0}%`}
                      />

                      <Divider />

                      <Score
                        label="Retrieval"
                        value={`${metrics.scores?.retrieval_relevance ?? 0}%`}
                      />

                    </div>

                    <div className="flex items-center gap-2">
                      <div className="text-right">
                        <div
                          className="text-[9px] tracking-[.13em]"
                          style={{ color: C.muted }}
                        >
                          EVIDENCE
                        </div>

                        <div
                          className="mt-0.5 text-xs font-semibold uppercase tracking-[.08em]"
                          style={{
                            color:
                              STATUS_COLORS[
                                outcomeStatus
                              ] || C.muted,
                          }}
                        >
                          {outcomeStatus}
                        </div>
                        
                        {outcomeStatus === "ABSTAINED" && metrics.abstention?.reason && (
                          <div
                            className="mt-1 max-w-[200px] text-[9px] leading-tight"
                            style={{ color: C.danger }}
                          >
                            {metrics.abstention.reason}
                          </div>
                        )}
                      </div>

                      <span
                        style={{
                          color:
                            STATUS_COLORS[
                              outcomeStatus
                            ] || C.muted,
                        }}
                      >
                        {getStatusIcon(outcomeStatus)}
                      </span>
                    </div>

                  </div>
                </div>
              </div>

              {/* ===========================================
                  FIXED GRAPH CANVAS
              ============================================ */}

              <div className="flex min-h-full min-w-full items-start justify-center px-10 pb-20 pt-8">

                {graphSvg ? (
                  <div
                    ref={graphRef}
                    className="ipshakti-eval-graph"
                    style={{
                      minHeight: GRAPH_MIN_HEIGHT,
                    }}
                    dangerouslySetInnerHTML={{
                      __html: graphSvg,
                    }}
                  />
                ) : (
                  <div
                    className="flex h-[500px] w-full items-center justify-center text-[10px] font-mono tracking-[.15em]"
                    style={{ color: C.muted }}
                  >
                    NO ORCHESTRATION GRAPH
                  </div>
                )}

              </div>
            </div>
          </section>

          {/* =================================================
              RESIZABLE NODE INSPECTOR
          ================================================= */}

          <section
            className="relative shrink-0 border-t bg-white"
            style={{
              height: inspectorHeight,
              borderColor: C.line,
            }}
          >

            {/* drag handle */}

            <div
              onMouseDown={() => setResizingInspector(true)}
              className="absolute -top-3 left-1/2 z-50 flex h-6 w-20 -translate-x-1/2 cursor-row-resize items-center justify-center rounded-full border bg-white shadow-sm"
              style={{ borderColor: C.line }}
              title="Drag upward to expand inspector"
            >
              <div className="flex gap-1">
                <span
                  className="h-1 w-1 rounded-full"
                  style={{ background: C.muted }}
                />
                <span
                  className="h-1 w-1 rounded-full"
                  style={{ background: C.muted }}
                />
                <span
                  className="h-1 w-1 rounded-full"
                  style={{ background: C.muted }}
                />
              </div>
            </div>

            {/* inspector header */}

            <div
              className="flex h-[64px] shrink-0 items-center justify-between border-b px-5"
              style={{
                borderColor: C.line,
                background: "#F7F4EB",
              }}
            >
              <div>
                <div
                  className="text-[9px] font-semibold tracking-[.16em]"
                  style={{ color: C.muted }}
                >
                  NODE INSPECTOR
                </div>

                <div
                  className="mt-1 text-[10px]"
                  style={{ color: C.muted2 }}
                >
                  Drag upward to expand references
                </div>
              </div>

              {selectedNode && (
                <span
                  className="rounded-full border bg-white px-2.5 py-1 font-mono text-[9px]"
                  style={{
                    borderColor: C.line,
                    color: C.muted,
                  }}
                >
                  /{selectedNode}
                </span>
              )}
            </div>

            {/* independently scrollable content */}

            <div className="h-[calc(100%-64px)] overflow-y-auto px-5 py-5">

              <AnimatePresence mode="wait">

                {!selectedNode ? (
                  <motion.div
                    key="empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    {metrics.trace && metrics.trace.length > 0 ? (
                      <div>
                        <div
                          className="mb-4 text-[9px] font-semibold tracking-[.14em]"
                          style={{ color: C.muted }}
                        >
                          EXECUTION TRACE
                        </div>
                        <div className="space-y-2">
                          {metrics.trace.map((step, i) => (
                            <div
                              key={i}
                              className="rounded border p-3 font-mono text-[10px] leading-relaxed"
                              style={{
                                borderColor: C.line,
                                background: C.paper,
                                color: C.ink,
                              }}
                            >
                              <div className="mb-1 text-[8px] font-bold text-muted">STEP {i + 1}</div>
                              {step}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div
                        className="flex min-h-[100px] items-center justify-center text-[10px] font-mono uppercase tracking-[.14em]"
                        style={{ color: C.muted2 }}
                      >
                        Click a graph node to inspect
                      </div>
                    )}
                  </motion.div>
                ) : (
                  <motion.div
                    key={selectedNode}
                    initial={{
                      opacity: 0,
                      y: 4,
                    }}
                    animate={{
                      opacity: 1,
                      y: 0,
                    }}
                    transition={{
                      duration: 0.18,
                    }}
                    className="space-y-5"
                  >

                    {/* Node heading */}

                    <div className="flex items-center gap-3">

                      <span
                        style={{
                          color:
                            STATUS_COLORS[
                              selectedStatus
                            ] || C.muted,
                        }}
                      >
                        {getStatusIcon(selectedStatus)}
                      </span>

                      <div>
                        <h3 className="text-sm font-bold capitalize">
                          {selectedNode.replace(
                            /_/g,
                            " "
                          )}
                        </h3>

                        <div
                          className="mt-0.5 font-mono text-[9px]"
                          style={{
                            color: C.muted,
                          }}
                        >
                          {selectedStatus}
                        </div>
                      </div>

                    </div>

                    {/* success */}

                    {selectedStatus === "VERIFIED" && (
                      <StatusMessage>
                        <Check size={14} />
                        Node executed successfully
                        with verified status.
                      </StatusMessage>
                    )}

                    {selectedStatus === "PASSED" && (
                      <StatusMessage>
                        <Check size={14} />
                        Execution completed with
                        passed status.
                      </StatusMessage>
                    )}

                    {/* supervisor */}

                    {selectedNode === "supervisor" && (
                      <div
                        className="rounded-xl border p-4"
                        style={{
                          borderColor: C.line,
                          background: C.paper,
                        }}
                      >
                        <div
                          className="text-[9px] font-semibold tracking-[.14em]"
                          style={{
                            color: C.muted,
                          }}
                        >
                          SUPERVISOR DETAILS
                        </div>

                        <div
                          className="mt-2 font-mono text-[10px]"
                          style={{
                            color: C.ink,
                          }}
                        >
                          Tasks Created:{" "}
                          {metrics.nodes?.supervisor?.details?.tasks_created ?? 0}
                        </div>
                      </div>
                    )}

                    {/* worker */}

                    {selectedNode === "worker" &&
                      tasks.length > 0 && (
                        <WorkerInspector
                          tasks={tasks}
                          metrics={metrics}
                        />
                      )}

                    {/* evidence verification */}

                    {selectedNode ===
                      "evidence_verification" && (
                      <div
                        className="rounded-xl border p-4"
                        style={{
                          borderColor: C.line,
                          background: C.paper,
                        }}
                      >
                        <div
                          className="text-[9px] font-semibold tracking-[.14em]"
                          style={{
                            color: C.muted,
                          }}
                        >
                          RULES APPLIED
                        </div>

                        <div
                          className="mt-2 text-xs leading-5"
                          style={{
                            color: C.muted,
                          }}
                        >
                          Enforcing task coverage and
                          structural constraints.
                        </div>

                        <div
                          className="mt-2 text-xs font-medium"
                          style={{
                            color: isAbstained
                              ? C.danger
                              : C.forest2,
                          }}
                        >
                          {isAbstained
                            ? metrics.abstention
                                ?.reason
                            : "Constraints met or partial coverage evaluated."}
                        </div>
                      </div>
                    )}

                    {/* validation */}

                    {selectedNode ===
                      "validate_response" && (
                      <div
                        className="rounded-xl border p-4"
                        style={{
                          borderColor: C.line,
                          background: C.paper,
                        }}
                      >
                        <div
                          className="text-[9px] font-semibold tracking-[.14em]"
                          style={{
                            color: C.muted,
                          }}
                        >
                          SEMANTIC VALIDATION
                        </div>

                        <div
                          className="mt-2 font-mono text-[10px]"
                          style={{
                            color: C.muted,
                          }}
                        >
                          Failures:{" "}
                          {metrics.nodes?.[
                            selectedNode
                          ]?.details?.failures || 0}
                        </div>

                        {metrics.nodes?.[
                          selectedNode
                        ]?.details?.feedback && (
                          <div
                            className="mt-3 rounded-lg border p-3 font-mono text-xs leading-5"
                            style={{
                              borderColor:
                                "#7A2E2E25",
                              background:
                                C.dangerSoft,
                              color: C.danger,
                            }}
                          >
                            {
                              metrics.nodes[
                                selectedNode
                              ].details.feedback
                            }
                          </div>
                        )}
                      </div>
                    )}

                  </motion.div>
                )}

              </AnimatePresence>

            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

/* =========================================================
   SCORE
========================================================= */

function Score({ label, value }) {
  return (
    <div className="flex flex-col">
      <span
        className="text-[9px] font-semibold tracking-[.12em]"
        style={{ color: C.muted }}
      >
        {label}
      </span>

      <span
        className="font-mono text-lg font-medium"
        style={{ color: C.ink }}
      >
        {value}
      </span>
    </div>
  );
}

function Divider() {
  return (
    <div
      className="h-7 w-px"
      style={{ background: C.line }}
    />
  );
}

/* =========================================================
   STATUS MESSAGE
========================================================= */

function StatusMessage({ children }) {
  return (
    <div
      className="flex items-center gap-1 text-xs"
      style={{ color: C.forest2 }}
    >
      {children}
    </div>
  );
}

/* =========================================================
   WORKER INSPECTOR
========================================================= */

function WorkerInspector({ tasks, metrics }) {
  const workerDetails = metrics?.nodes?.worker?.details;

  return (
    <div className="flex flex-col gap-4">

      {workerDetails && (
        <div className="flex gap-4 rounded-xl border bg-[#F9F9F9] p-4" style={{ borderColor: C.line }}>
          <div className="flex flex-col">
            <span className="text-[9px] font-bold tracking-[.1em]" style={{ color: C.muted }}>EXECUTED</span>
            <span className="font-mono text-sm" style={{ color: C.ink }}>{workerDetails.tasks_executed}</span>
          </div>
          <Divider />
          <div className="flex flex-col">
            <span className="text-[9px] font-bold tracking-[.1em]" style={{ color: C.muted }}>SUFFICIENT</span>
            <span className="font-mono text-sm" style={{ color: C.ink }}>{workerDetails.tasks_sufficient}</span>
          </div>
        </div>
      )}

      <div
        className="text-[9px] font-semibold tracking-[.14em]"
        style={{ color: C.muted }}
      >
        RESEARCH TASKS & REFERENCED CHUNKS
      </div>

      {tasks.map((task, taskIndex) => {

        const chunks =
          task.chunks ||
          task.retrieved_chunks ||
          task.references ||
          task.evidence ||
          task.source_chunks ||
          [];

        const hasChunks =
          Array.isArray(chunks) &&
          chunks.length > 0;

        const hasText =
          hasChunks &&
          chunks.some(
            (chunk) =>
              chunk?.text ||
              chunk?.content ||
              chunk?.chunk_text ||
              chunk?.snippet ||
              chunk?.context
          );

        return (
          <div
            key={task.task_id || taskIndex}
            className="overflow-hidden rounded-xl border"
            style={{
              borderColor: C.line,
              background: C.paper,
            }}
          >

            {/* task heading */}

            <div
              className="flex flex-col gap-2 border-b bg-white p-4"
              style={{
                borderColor: C.line,
              }}
            >

              <div className="flex items-start gap-3">

                <span
                  className="mt-0.5 font-mono text-xs font-bold"
                  style={{ color: C.muted }}
                >
                  {String(taskIndex + 1).padStart(
                    2,
                    "0"
                  )}
                </span>

                <span className="text-xs font-medium leading-relaxed">
                  {task.question ||
                    task.task ||
                    "Unnamed research task"}
                </span>

              </div>

              <span
                className="pl-7 font-mono text-[10px]"
                style={{ color: C.muted }}
              >
                Retrieved:{" "}
                {task.retrieved_count || task.chunks_retrieved || chunks.length}
                {" · "}
                Relevant:{" "}
                {task.relevant_count ?? 0}
                {" · "}
                Mean sim:{" "}
                {task.mean_similarity ? Number(task.mean_similarity).toFixed(2) : "0.00"}
                {" · "}
                Max sim:{" "}
                {task.max_similarity ? Number(task.max_similarity).toFixed(2) : "0.00"}
              </span>

            </div>

            {task.reason && (
              <div className="border-b px-4 py-3 font-mono text-[9px]" style={{ borderColor: C.line, background: "#FEF7E6", color: "#8E601C" }}>
                <strong>NOTE:</strong> {task.reason}
              </div>
            )}

            {/* chunks */}

            <div className="flex flex-col gap-6 p-4">

              {!hasChunks && (
                <div
                  className="text-xs italic"
                  style={{
                    color: C.muted,
                  }}
                >
                  No retrieved chunks for this task.
                </div>
              )}

              {hasChunks && !hasText && (
                <div
                  className="rounded-lg border p-3 text-xs italic"
                  style={{
                    borderColor: C.line,
                    color: C.muted,
                    background: "#FFFDF7",
                  }}
                >
                  The evaluation response contains
                  retrieval metadata but not the full
                  retrieved chunk text.
                </div>
              )}

              {hasChunks &&
                chunks.map((chunk, chunkIndex) => {

                  const chunkText =
                    chunk?.text ||
                    chunk?.content ||
                    chunk?.chunk_text ||
                    chunk?.snippet ||
                    chunk?.context;

                  if (!chunkText) {
                    return null;
                  }

                  const sourceName =
                    chunk?.metadata?.source ||
                    chunk?.metadata?.title ||
                    chunk?.source ||
                    chunk?.title;

                  const page =
                    chunk?.metadata?.page ||
                    chunk?.page;

                  const score =
                    chunk?.score ??
                    chunk?.similarity ??
                    chunk?.metadata?.score ??
                    chunk?.metadata?.similarity;

                  const isRelevant = chunk?.is_relevant !== false;

                  return (
                    <div
                      key={chunkIndex}
                      className="flex flex-col gap-2 transition-opacity"
                      style={{ opacity: isRelevant ? 1 : 0.4 }}
                    >
                      <div className="flex items-center justify-between">
                        <div
                          className="text-[9px] font-semibold tracking-[.14em]"
                          style={{
                            color: C.muted,
                          }}
                        >
                          REFERENCED CHUNK{" "}
                          {String(
                            chunkIndex + 1
                          ).padStart(2, "0")}
                          {!isRelevant && (
                            <span className="ml-2 rounded px-1.5 py-0.5 text-[8px] font-bold" style={{ background: "#EAE7DD", color: C.muted2 }}>
                              IRRELEVANT
                            </span>
                          )}
                        </div>
                        {score !== undefined && score !== null && (
                          <div
                            className="font-mono text-[9px] font-medium"
                            style={{ color: C.muted2 }}
                          >
                            SCORE: {Number(score).toFixed(4)}
                          </div>
                        )}
                      </div>

                      {sourceName && (
                        <div
                          className="text-[11px] font-bold"
                          style={{
                            color: C.ink,
                          }}
                        >
                          {sourceName}
                          {page && (
                            <span
                              className="ml-2 font-mono font-normal"
                              style={{
                                color: C.muted,
                              }}
                            >
                              p.{page}
                            </span>
                          )}
                        </div>
                      )}

                      <div
                        className="rounded-lg border bg-white p-4 text-xs leading-6 whitespace-pre-wrap"
                        style={{
                          borderColor: C.line,
                          color: "#495245",
                        }}
                      >
                        {chunkText}
                      </div>

                    </div>
                  );
                })}

            </div>
          </div>
        );
      })}
    </div>
  );
}

export default EvalDashboard;
