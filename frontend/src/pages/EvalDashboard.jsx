import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import mermaid from "mermaid";
import api from "../api/client";

function EvalDashboard() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState(null);
  const [graphStr, setGraphStr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState(null);

  useEffect(() => {
    mermaid.initialize({ startOnLoad: true, theme: "default", securityLevel: 'loose' });
    window.handleNodeClick = (nodeId) => {
      setSelectedNode(nodeId);
    };
    return () => {
      delete window.handleNodeClick;
    };
  }, []);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [graphRes, metricsRes] = await Promise.all([
          api.get('/api/eval/graph'),
          api.get(`/api/eval/metrics/${sessionId}`)
        ]);
        
        let modifiedGraph = graphRes.graph || "";
        const STATUS_COLORS = {
          VERIFIED: "#10b981",
          PASSED: "#10b981",
          PARTIAL: "#f59e0b",
          ABSTAINED: "#ef4444",
          FAILED: "#ef4444",
          INSUFFICIENT: "#ef4444",
          PENDING: "#6b7280",
          SKIPPED: "#6b7280",
          UNAVAILABLE: "#9ca3af"
        };
        
        if (metricsRes && metricsRes.nodes) {
          const styles = [];
          const clicks = [];
          Object.entries(metricsRes.nodes).forEach(([node, nodeData]) => {
             const color = STATUS_COLORS[nodeData.status] || STATUS_COLORS.UNAVAILABLE;
             styles.push(`style ${node} fill:${color},color:#fff,stroke:#333,stroke-width:2px`);
             clicks.push(`click ${node} call handleNodeClick("${node}")`);
          });
          modifiedGraph = modifiedGraph + '\n' + styles.join('\n') + '\n' + clicks.join('\n');
        }
        
        setGraphStr(modifiedGraph);
        setMetrics(metricsRes);
        
        if (modifiedGraph) {
          setTimeout(() => {
            mermaid.contentLoaded();
          }, 100);
        }
      } catch (e) {
        console.error("Error fetching eval data", e);
      } finally {
        setLoading(false);
      }
    };
    if (sessionId) {
      fetchData();
    }
  }, [sessionId]);

  if (loading) {
    return <div style={{ padding: 40, fontFamily: "sans-serif" }}>Loading evaluation data...</div>;
  }

  const STATUS_COLORS = {
    VERIFIED: "#10b981",
    PASSED: "#10b981",
    PARTIAL: "#f59e0b",
    ABSTAINED: "#ef4444",
    FAILED: "#ef4444",
    INSUFFICIENT: "#ef4444",
    PENDING: "#6b7280",
    SKIPPED: "#6b7280",
    UNAVAILABLE: "#9ca3af"
  };

  const outcomeStatus = metrics.outcome?.status || "UNAVAILABLE";
  const isAbstained =
    typeof metrics.outcome?.is_abstained === "boolean"
      ? metrics.outcome.is_abstained
      : null;
  const statusColor = STATUS_COLORS[outcomeStatus] || STATUS_COLORS.UNAVAILABLE;
  const tasks = metrics.tasks || [];

  return (
    <div style={{ flex: 1, padding: "24px", overflowY: "auto", background: "#f8f9fa", color: "#1f2937", fontFamily: "sans-serif" }}>
      <button onClick={() => navigate("/")} style={{ marginBottom: 16, cursor: "pointer", padding: "8px 16px", border: "1px solid #ddd", borderRadius: 4, background: "#fff", fontWeight: "bold" }}>
        ← Back to Chat
      </button>

      <h1 style={{ marginBottom: 24, fontSize: 24, fontWeight: "bold" }}>Session Evaluation ({sessionId})</h1>

      {/* Evaluation Summary */}
      <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', padding: 20, marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 16, borderBottom: '1px solid #eee', paddingBottom: 8 }}>Evaluation Summary</h2>
        <div style={{ display: 'flex', gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase' }}>Confidence Heuristic</div>
            <div style={{ fontSize: 24, fontWeight: 'bold' }}>
              {typeof metrics.scores?.confidence_heuristic === "number" ? metrics.scores.confidence_heuristic : "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase' }}>Task Coverage</div>
            <div style={{ fontSize: 24, fontWeight: 'bold' }}>
              {typeof metrics.scores?.task_coverage === "number" ? `${metrics.scores.task_coverage}%` : "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase' }}>Evidence Status</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: statusColor }}>{outcomeStatus}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase' }}>Outcome</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: isAbstained === true ? STATUS_COLORS.ABSTAINED : (outcomeStatus === "UNAVAILABLE" ? STATUS_COLORS.UNAVAILABLE : STATUS_COLORS.PASSED) }}>
              {isAbstained === true ? "ABSTAINED" : (outcomeStatus === "UNAVAILABLE" ? "—" : "ANSWERED")}
            </div>
          </div>
        </div>
      </div>

      {/* Orchestration Graph */}
      <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', padding: 20, marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, marginBottom: 16, borderBottom: '1px solid #eee', paddingBottom: 8 }}>Agent Orchestration Graph</h2>
        <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
           ───── EXECUTION ───── (Supervisor → Workers → Retrieval) <br/>
           ───── VERIFICATION ───── (Evidence Gate) <br/>
           ───── OUTPUT ───── (Generate → Confidence)
        </p>
        <div style={{ overflowX: "auto", textAlign: "center" }}>
           {graphStr ? (
             <div className="mermaid" key={graphStr.length}>
               {graphStr}
             </div>
           ) : (
             <p>No graph data available</p>
           )}
           <p style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>Click on colored nodes (e.g., worker, evidence_verification, generate) to view details.</p>
        </div>
      </div>

      {/* Selected Node Details */}
      {selectedNode && (
        <div style={{ display: 'flex', gap: 24, marginBottom: 24 }}>
          {/* Left panel: Selected Node overview */}
          <div style={{ flex: 1, background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', padding: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 'bold', marginBottom: 8, textTransform: 'capitalize' }}>Node: {selectedNode.replace(/_/g, ' ')}</h3>
            {metrics.nodes?.[selectedNode] ? (
              <>
                <div style={{ fontSize: 18, fontWeight: 'bold', color: STATUS_COLORS[metrics.nodes[selectedNode].status] || STATUS_COLORS.UNAVAILABLE, marginBottom: 16 }}>
                  {metrics.nodes[selectedNode].status === 'PASSED' || metrics.nodes[selectedNode].status === 'VERIFIED' ? '✓' : '⚠'} {metrics.nodes[selectedNode].status}
                </div>
                
                {selectedNode === 'worker' && (
                  <>
                    <h4 style={{ fontSize: 14, fontWeight: 'bold', marginTop: 16 }}>Research Tasks</h4>
                    <ul style={{ listStyleType: 'none', padding: 0, fontSize: 14 }}>
                      {tasks.map(t => (
                         <li key={t.task_id} style={{ margin: '8px 0', borderLeft: `3px solid ${STATUS_COLORS[t.status] || '#ef4444'}`, paddingLeft: 8 }}>
                           <div style={{ fontWeight: "500" }}>{t.question}</div>
                           <div style={{ color: STATUS_COLORS[t.status] || '#ef4444', fontSize: 12, marginBottom: t.chunks?.length ? 8 : 0 }}>
                             {t.status === 'PASSED' ? `✓ Retrieved ${t.relevant_count} relevant chunks (Max Sim: ${t.max_similarity})` : `⚠ Insufficient: ${t.reason || 'Missing evidence'}`}
                           </div>
                           
                           {t.chunks && t.chunks.length > 0 && (
                             <details style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 4, padding: '8px 12px', fontSize: 12, color: '#374151', marginBottom: 4 }}>
                               <summary style={{ cursor: 'pointer', fontWeight: 500, userSelect: 'none', color: '#4b5563' }}>
                                 View Retrieved Chunks ({t.chunks.length})
                               </summary>
                               <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
                                 {t.chunks.map((c, i) => (
                                   <div key={i} style={{ 
                                     background: '#fff', 
                                     padding: 10, 
                                     borderRadius: 4, 
                                     border: `1px solid ${c.is_relevant ? '#10b981' : '#e5e7eb'}`,
                                     borderLeft: `3px solid ${c.is_relevant ? '#10b981' : '#9ca3af'}`
                                   }}>
                                     <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                       <strong>{c.act_name} {c.section_or_article ? `- ${c.section_or_article}` : ''}</strong>
                                       <span style={{ 
                                         background: c.is_relevant ? '#d1fae5' : '#f3f4f6', 
                                         color: c.is_relevant ? '#065f46' : '#4b5563', 
                                         padding: '2px 6px', 
                                         borderRadius: 4, 
                                         fontWeight: 600 
                                       }}>
                                         Sim: {c.similarity}
                                       </span>
                                     </div>
                                     <div style={{ fontStyle: 'italic', color: '#6b7280', fontSize: 11, marginBottom: 4 }}>
                                       Page {c.page_start} • {c.is_relevant ? 'Passed Relevance Threshold' : 'Ignored (Below Threshold)'}
                                     </div>
                                     <div style={{ lineHeight: 1.4 }}>
                                       "{c.snippet}"
                                     </div>
                                   </div>
                                 ))}
                               </div>
                             </details>
                           )}
                         </li>
                      ))}
                    </ul>
                  </>
                )}
    
                {selectedNode === 'evidence_verification' && (
                  <>
                    <h4 style={{ fontSize: 14, fontWeight: 'bold', marginTop: 16 }}>Verification Rules Applied</h4>
                    <ul style={{ listStyleType: 'disc', paddingLeft: 20, fontSize: 14, color: '#4b5563' }}>
                      <li>Checking task coverage across all domains.</li>
                      <li>Enforcing case law / judgement presence if requested.</li>
                    </ul>
                    <div style={{ marginTop: 16, padding: 12, background: '#f3f4f6', borderRadius: 6, fontSize: 14, fontStyle: 'italic', color: '#4b5563' }}>
                      {metrics.nodes[selectedNode].status === "PASSED" 
                        ? "All required evidence constraints met." 
                        : (isAbstained ? metrics.abstention?.reason : "Partial coverage: some required evidence is missing or downgraded.")}
                    </div>
                  </>
                )}
    
                {selectedNode === 'generate' && (
                  <>
                    <h4 style={{ fontSize: 14, fontWeight: 'bold', marginTop: 16 }}>Generation Info</h4>
                    <ul style={{ listStyleType: 'disc', paddingLeft: 20, fontSize: 14, color: '#4b5563' }}>
                      <li>Grounded exclusively in retrieved corpus chunks (Max 8 per task).</li>
                      {outcomeStatus !== 'VERIFIED' && <li style={{color: '#ef4444'}}>Conclusive language prohibited due to evidence gaps.</li>}
                    </ul>
                  </>
                )}
                
                {['supervisor', 'log_and_serve'].includes(selectedNode) && (
                  <p style={{ fontSize: 14, color: '#6b7280' }}>Node executed successfully.</p>
                )}
              </>
            ) : (
              <p>No details available for this node.</p>
            )}
          </div>
          
          {/* Right panel: Evaluation Details (Global metrics for context) */}
          <div style={{ flex: 1, background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', padding: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 'bold', marginBottom: 16 }}>Session Context</h3>
            
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, marginBottom: 4 }}>
                <span>Coverage</span>
                <span>{typeof metrics.scores?.task_coverage === "number" ? `${metrics.scores.task_coverage}%` : "—"}</span>
              </div>
              <div style={{ width: '100%', background: '#e5e7eb', height: 6, borderRadius: 3 }}>
                <div style={{ width: `${typeof metrics.scores?.task_coverage === "number" ? metrics.scores.task_coverage : 0}%`, background: statusColor, height: '100%', borderRadius: 3 }}></div>
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, marginBottom: 4 }}>
                <span>Retrieval Relevance</span>
                <span>{typeof metrics.scores?.retrieval_relevance === "number" ? `${metrics.scores.retrieval_relevance}%` : "—"}</span>
              </div>
              <div style={{ width: '100%', background: '#e5e7eb', height: 6, borderRadius: 3 }}>
                <div style={{ width: `${typeof metrics.scores?.retrieval_relevance === "number" ? metrics.scores.retrieval_relevance : 0}%`, background: '#3b82f6', height: '100%', borderRadius: 3 }}></div>
              </div>
            </div>
            
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, marginBottom: 4 }}>
                <span title="Not implemented for this session" style={{ cursor: "help" }}>Claim Grounding ℹ️</span>
                <span>—</span>
              </div>
            </div>
            
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, marginBottom: 4 }}>
                <span title="Not implemented for this session" style={{ cursor: "help" }}>Citation Accuracy ℹ️</span>
                <span>—</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Failure / Abstention Analysis */}
      {(isAbstained || outcomeStatus === "PARTIAL") && (
        <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', padding: 20, borderLeft: `4px solid ${isAbstained ? STATUS_COLORS.ABSTAINED : STATUS_COLORS.PARTIAL}` }}>
          <h2 style={{ fontSize: 16, marginBottom: 16, fontWeight: 'bold', color: isAbstained ? STATUS_COLORS.ABSTAINED : STATUS_COLORS.PARTIAL }}>
            {isAbstained ? "⛔ Abstention Analysis" : "⚠ Evidence Gap"}
          </h2>
          <div style={{ fontSize: 14, marginBottom: 16 }}>
            <strong>Status:</strong> {isAbstained ? "ABSTAINED" : "PARTIAL"}
          </div>
          <div style={{ fontSize: 14, marginBottom: 16 }}>
            <strong>Reason:</strong> {metrics.abstention?.reason || "Required evidence was not found in the corpus."}
          </div>
          
          {tasks.filter(t => !t.sufficient).length > 0 && (
            <>
              <h3 style={{ fontSize: 14, fontWeight: 'bold', marginTop: 16, marginBottom: 8 }}>Insufficient Tasks</h3>
              <ul style={{ listStyleType: 'disc', paddingLeft: 20, fontSize: 14, color: '#4b5563' }}>
                {tasks.filter(t => !t.sufficient).map(t => (
                  <li key={t.task_id} style={{ marginBottom: 4 }}>
                    <strong>{t.question}</strong>
                    <br/>
                    Root cause: {t.reason || 'Missing evidence'}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

    </div>
  );
}

export default EvalDashboard;
