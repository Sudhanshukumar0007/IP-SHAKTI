import { Leaf, MessageSquare, Lock, User, ChevronRight, Plus } from "lucide-react";

function Sidebar({
  chatHistory,
  onNewChat,
  onSelectChat,
  activeChatId,
  isOpen,
  onClose,
  onOpenFacilitator
}) {
  // Deduplicate chat history by id
  const uniqueHistory = Array.from(new Map(chatHistory.map(item => [item.id, item])).values());

  return (
    <aside className={`
      fixed inset-y-0 left-0 z-40 w-72 flex flex-col bg-zinc-950 text-zinc-100 border-r border-zinc-800/50 
      transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]
      ${isOpen ? 'translate-x-0' : '-translate-x-full'} md:relative md:translate-x-0
    `}>
      {/* =====================================
          LOGO
      ===================================== */}
      <div className="flex items-center justify-between p-6 pb-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-forest/20 border border-forest/30 text-forest-light">
            <Leaf size={20} strokeWidth={1.5} />
          </div>
          <div className="flex flex-col">
            <strong className="text-lg font-bold tracking-tight leading-none text-zinc-50">IP-SAKTI</strong>
            <span className="text-sm text-zinc-400 font-medium">Sahayak</span>
          </div>
        </div>
        <button 
          className="md:hidden p-2 text-zinc-400 hover:text-zinc-50 rounded-lg hover:bg-zinc-900 transition-colors" 
          onClick={onClose}
          aria-label="Close sidebar"
        >
          <span className="text-2xl leading-none">&times;</span>
        </button>
      </div>

      {/* =====================================
          NEW CHAT
      ===================================== */}
      <div className="px-6 py-4">
        <button 
          data-testid="new-chat-button" 
          className="flex items-center justify-center gap-2 w-full py-2.5 px-4 bg-zinc-50 hover:bg-zinc-200 text-zinc-950 font-medium rounded-xl transition-all duration-300 ease-out active:scale-[0.98]"
          onClick={onNewChat}
        >
          <Plus size={16} strokeWidth={2} />
          New conversation
        </button>
      </div>

      {/* =====================================
          HISTORY
      ===================================== */}
      <div className="flex-1 flex flex-col min-h-0 overflow-y-auto px-4 pb-4">
        <div className="flex items-center justify-between px-2 py-3 mt-2">
          <span className="text-[11px] font-bold tracking-widest text-zinc-500 uppercase">Your Sessions</span>
          <span className="text-[11px] font-mono text-zinc-600">{uniqueHistory.length}</span>
        </div>
        
        <div className="flex flex-col gap-1">
          {uniqueHistory.map((chat) => (
            <button
              key={chat.id}
              className={`
                group flex items-start gap-3 p-3 w-full text-left rounded-xl transition-all duration-200 ease-out
                ${chat.id === activeChatId 
                  ? 'bg-zinc-900/80 text-zinc-50 border border-zinc-800' 
                  : 'text-zinc-400 hover:bg-zinc-900/50 hover:text-zinc-200 border border-transparent'}
              `}
              onClick={() => onSelectChat(chat.id)}
            >
              <MessageSquare size={16} strokeWidth={1.5} className={`mt-0.5 shrink-0 ${chat.id === activeChatId ? 'text-forest-light' : 'text-zinc-600 group-hover:text-zinc-400 transition-colors'}`} />
              <div className="flex flex-col min-w-0">
                <span className="text-sm font-medium truncate">
                  {chat.title || "New conversation"}
                </span>
                <span className="text-xs text-zinc-500 mt-1 truncate">
                  {chat.metadata || "Today · 0 sources"}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* =====================================
          SIDEBAR FOOTER
      ===================================== */}
      <div className="p-4 mt-auto border-t border-zinc-900">
        <button 
          data-testid="facilitator-button" 
          className="flex items-center justify-between w-full p-3 mb-2 rounded-xl text-zinc-400 hover:text-zinc-50 hover:bg-zinc-900 transition-colors group"
          onClick={onOpenFacilitator}
        >
          <div className="flex items-center gap-3">
            <User size={16} strokeWidth={1.5} className="group-hover:text-forest-light transition-colors" />
            <span className="text-sm font-medium">Talk to a facilitator</span>
          </div>
          <ChevronRight size={16} strokeWidth={1.5} className="text-zinc-600 group-hover:text-zinc-400 transition-transform group-hover:translate-x-0.5" />
        </button>
        
        <div className="flex items-start gap-3 p-3 bg-zinc-900/50 rounded-xl border border-zinc-800/50">
          <Lock size={14} strokeWidth={1.5} className="text-forest-light mt-0.5 shrink-0" />
          <div className="flex flex-col min-w-0">
            <strong className="text-[11px] font-medium text-zinc-300 leading-tight">Your conversations stay private</strong>
            <span className="text-[10px] text-zinc-500 mt-0.5 truncate">DPDP-aligned · Demo workspace</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;