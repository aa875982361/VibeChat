"use client";

import {
  Check,
  HeartHandshake,
  Loader2,
  LogIn,
  MessageCircle,
  RefreshCcw,
  Send,
  Shield,
  Sparkles,
  Users
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AnalyzeResponse,
  JoinRoomResponse,
  Message,
  Room,
  Session,
  analyzeEmotion,
  createSession,
  joinRoom,
  listRooms,
  rejoinRoom
} from "../lib/api";

const emotionNames: Record<string, string> = {
  joy: "开心",
  sadness: "难过",
  anxiety: "焦虑",
  anger: "生气",
  loneliness: "孤独",
  stress: "压力",
  gratitude: "感谢",
  shame: "羞耻",
  confusion: "混乱",
  neutral: "平静"
};

const samples = ["今天升职了但不敢发朋友圈", "我很难过但不想朋友担心", "压力好大，想找个地方说说"];

function formatMessageTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [text, setText] = useState("");
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [chat, setChat] = useState<JoinRoomResponse | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState<"session" | "analysis" | "join" | null>("session");
  const [enteringRoomId, setEnteringRoomId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [presence, setPresence] = useState("");
  const [socketReady, setSocketReady] = useState(false);
  const [statusShareChoice, setStatusShareChoice] = useState<"pending" | "sent" | "dismissed">("pending");
  const [statusDraft, setStatusDraft] = useState("");
  const socketRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      try {
        const cached = localStorage.getItem("vibechat-session");
        if (cached) {
          setSession(JSON.parse(cached) as Session);
        } else {
          const nextSession = await createSession();
          if (!cancelled) {
            setSession(nextSession);
            localStorage.setItem("vibechat-session", JSON.stringify(nextSession));
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "匿名身份创建失败");
      } finally {
        if (!cancelled) setLoading(null);
      }
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    listRooms(session.session_id)
      .then((nextRooms) => {
        if (!cancelled) setRooms(nextRooms);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [analysis?.analysis_id, chat?.room.id, session?.session_id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, presence]);

  useEffect(() => {
    if (analysis?.analysis.status_message) {
      setStatusDraft(analysis.analysis.status_message);
    }
  }, [analysis]);

  const canAnalyze = useMemo(() => text.trim().length >= 2 && !loading && session, [text, loading, session]);
  const myRooms = useMemo(() => rooms.filter((room) => room.joined_by_me), [rooms]);
  const publicRooms = useMemo(() => rooms.filter((room) => !room.joined_by_me), [rooms]);

  async function handleAnalyze(event: FormEvent) {
    event.preventDefault();
    if (!session || !canAnalyze) return;
    setError("");
    setAnalysis(null);
    setChat(null);
    setStatusShareChoice("pending");
    closeSocket();
    setLoading("analysis");
    try {
      const result = await analyzeEmotion(session.session_id, text.trim());
      setAnalysis(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析失败，请稍后再试。");
    } finally {
      setLoading(null);
    }
  }

  async function handleJoin() {
    if (!session || !analysis) return;
    setError("");
    setLoading("join");
    setEnteringRoomId(null);
    try {
      const joined = await joinRoom(session.session_id, analysis.analysis_id);
      setChat(joined);
      setMessages(joined.messages);
      setStatusShareChoice("pending");
      connectSocket(joined.ws_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "进入房间失败。");
    } finally {
      setLoading(null);
    }
  }

  async function handleRejoin(roomId: string) {
    if (!session) return;
    setError("");
    setLoading("join");
    setEnteringRoomId(roomId);
    closeSocket();
    try {
      const joined = await rejoinRoom(session.session_id, roomId);
      setAnalysis(null);
      setChat(joined);
      setMessages(joined.messages);
      setPresence("");
      setStatusShareChoice("dismissed");
      setStatusDraft("");
      connectSocket(joined.ws_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "进入房间失败。");
    } finally {
      setLoading(null);
      setEnteringRoomId(null);
    }
  }

  function connectSocket(url: string) {
    closeSocket();
    const socket = new WebSocket(url);
    socketRef.current = socket;
    socket.onopen = () => setSocketReady(true);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as
        | { type: "message"; message: Message }
        | {
            type: "presence";
            event: "join" | "leave";
            display_name: string;
            online_count: number;
            participant_count: number;
          }
        | { type: "error"; message: string };
      if (payload.type === "message") {
        setMessages((current) => [...current, payload.message]);
        return;
      }
      if (payload.type === "presence") {
        setPresence(`${payload.display_name} ${payload.event === "join" ? "进入了房间" : "离开了房间"}`);
        setChat((current) =>
          current
            ? {
                ...current,
                room: {
                  ...current.room,
                  online_count: payload.online_count,
                  participant_count: payload.participant_count
                }
              }
            : current
        );
        return;
      }
      setError(payload.message);
    };
    socket.onerror = () => {
      setSocketReady(false);
      setError("聊天室连接暂时不稳定。");
    };
    socket.onclose = () => setSocketReady(false);
  }

  function closeSocket() {
    socketRef.current?.close();
    socketRef.current = null;
    setSocketReady(false);
  }

  function sendMessage(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || socketRef.current?.readyState !== WebSocket.OPEN) return;
    socketRef.current.send(JSON.stringify({ content }));
    setDraft("");
  }

  function sendCurrentStatus() {
    const content = statusDraft.trim();
    if (!content || socketRef.current?.readyState !== WebSocket.OPEN) return;
    socketRef.current.send(JSON.stringify({ content }));
    setStatusShareChoice("sent");
  }

  function resetFlow() {
    setAnalysis(null);
    setChat(null);
    setText("");
    setMessages([]);
    setPresence("");
    setError("");
    setStatusShareChoice("pending");
    setStatusDraft("");
    closeSocket();
  }

  return (
    <main className="min-h-screen px-4 py-5 sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-40px)] w-full max-w-7xl flex-col gap-5 lg:flex-row">
        <section className="flex min-h-[560px] flex-1 flex-col rounded-[8px] border border-white/70 bg-white/78 shadow-calm backdrop-blur">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/10 px-5 py-4">
            <div>
              <div className="flex items-center gap-2 text-sm font-medium text-tide">
                <Sparkles size={16} />
                VibeChat
              </div>
              <h1 className="mt-1 text-2xl font-semibold tracking-normal text-ink sm:text-3xl">把此刻的情绪放在匿名同频里</h1>
            </div>
            <div className="flex items-center gap-2 rounded-[8px] border border-moss/20 bg-mist px-3 py-2 text-sm text-ink/70">
              <Shield size={16} />
              {session ? session.display_name : "正在生成匿名身份"}
            </div>
          </header>

          {!chat ? (
            <div className="grid flex-1 gap-0 lg:grid-cols-[1.08fr_0.92fr]">
              <form onSubmit={handleAnalyze} className="flex flex-col gap-4 border-b border-ink/10 p-5 lg:border-b-0 lg:border-r">
                <label className="text-sm font-medium text-ink/70" htmlFor="emotion-text">
                  现在想说什么
                </label>
                <textarea
                  id="emotion-text"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  className="min-h-[250px] flex-1 resize-none rounded-[8px] border border-ink/12 bg-[#fbfaf7] p-4 text-base leading-7 text-ink outline-none transition focus:border-tide focus:ring-4 focus:ring-tide/10"
                  placeholder="可以是开心、难过、焦虑、委屈，也可以只是一个不想发朋友圈的瞬间。"
                  maxLength={2000}
                />
                <div className="flex flex-wrap gap-2">
                  {samples.map((sample) => (
                    <button
                      type="button"
                      key={sample}
                      onClick={() => setText(sample)}
                      className="rounded-[8px] border border-ink/10 bg-white px-3 py-2 text-sm text-ink/65 transition hover:border-tide/40 hover:text-ink"
                    >
                      {sample}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-ink/55">{text.length}/2000</p>
                  <button
                    type="submit"
                    disabled={!canAnalyze}
                    className="inline-flex min-h-11 items-center gap-2 rounded-[8px] bg-ink px-5 py-3 text-sm font-medium text-white transition hover:bg-tide disabled:cursor-not-allowed disabled:bg-ink/35"
                  >
                    {loading === "analysis" ? <Loader2 className="animate-spin" size={17} /> : <HeartHandshake size={17} />}
                    识别并匹配
                  </button>
                </div>
              </form>

              <aside className="flex flex-col gap-4 p-5">
                {analysis ? (
                  analysis.safe_to_join ? (
                    <AnalysisPanel analysis={analysis} onJoin={handleJoin} joining={loading === "join"} />
                  ) : (
                    <SafetyPanel analysis={analysis} onReset={resetFlow} />
                  )
                ) : (
                  <EmptyPanel loading={loading === "session"} />
                )}
                {error ? <div className="rounded-[8px] border border-clay/25 bg-clay/10 px-4 py-3 text-sm text-clay">{error}</div> : null}
              </aside>
            </div>
          ) : (
            <section className="flex min-h-0 flex-1 flex-col">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/10 px-5 py-4">
                <div>
                  <div className="flex items-center gap-2 text-sm text-tide">
                    <MessageCircle size={16} />
                    {chat.room.name}
                  </div>
                  <p className="mt-1 max-w-2xl text-sm text-ink/62">{chat.room.description}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="inline-flex items-center gap-2 rounded-[8px] bg-mist px-3 py-2 text-sm text-ink/65">
                    <Users size={16} />
                    {chat.room.online_count} 在线 · {chat.room.participant_count} 人来过
                  </span>
                  <span
                    className={`inline-flex items-center gap-2 rounded-[8px] px-3 py-2 text-sm ${
                      socketReady ? "bg-moss/12 text-moss" : "bg-clay/10 text-clay"
                    }`}
                  >
                    <span className={`h-2 w-2 rounded-full ${socketReady ? "bg-moss" : "bg-clay"}`} />
                    {socketReady ? "已连接" : "连接中"}
                  </span>
                  <button
                    type="button"
                    onClick={resetFlow}
                    className="inline-flex items-center gap-2 rounded-[8px] border border-ink/10 bg-white px-3 py-2 text-sm text-ink/70 transition hover:border-tide/40"
                  >
                    <RefreshCcw size={16} />
                    重新匹配
                  </button>
                </div>
              </div>

              <div className="scroll-soft flex-1 overflow-y-auto px-5 py-5">
                <div className="mx-auto flex max-w-3xl flex-col gap-3">
                  {presence ? <div className="self-center rounded-[8px] bg-mist px-3 py-1.5 text-xs text-ink/55">{presence}</div> : null}
                  {analysis && statusShareChoice === "pending" ? (
                    <CurrentStatusPanel
                      value={statusDraft}
                      disabled={!socketReady || !statusDraft.trim()}
                      onChange={setStatusDraft}
                      onSend={sendCurrentStatus}
                      onDismiss={() => setStatusShareChoice("dismissed")}
                    />
                  ) : null}
                  {analysis && statusShareChoice === "sent" ? (
                    <div className="self-center rounded-[8px] bg-mist px-3 py-1.5 text-xs text-ink/55">当前状态已发送</div>
                  ) : null}
                  {messages.length === 0 ? (
                    <div className="rounded-[8px] border border-dashed border-ink/16 bg-white/60 p-5 text-center text-sm text-ink/55">
                      {chat.room.online_count <= 1
                        ? "暂时还没有同频用户在线。房间已经为你保留，可以先留下一句当前状态，也可以安静地等下一个相近情绪的人进来。"
                        : "房间已经准备好。你可以先说一句，也可以安静地等别人开口。"}
                    </div>
                  ) : null}
                  {messages.map((message) => {
                    const mine = message.session_id === session?.session_id;
                    const time = formatMessageTime(message.created_at);
                    return (
                      <article key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                        <div
                          className={`max-w-[82%] rounded-[8px] px-4 py-3 text-sm leading-6 ${
                            mine ? "bg-ink text-white" : "border border-ink/10 bg-white text-ink"
                          }`}
                        >
                          <div
                            className={`mb-1 flex items-center justify-between gap-4 text-xs ${
                              mine ? "text-white/65" : "text-ink/45"
                            }`}
                          >
                            <span>{message.display_name}</span>
                            {time ? <span>{time}</span> : null}
                          </div>
                          <p className="whitespace-pre-wrap break-words">{message.content}</p>
                        </div>
                      </article>
                    );
                  })}
                  <div ref={bottomRef} />
                </div>
              </div>

              <form onSubmit={sendMessage} className="border-t border-ink/10 p-4">
                <div className="mx-auto flex max-w-3xl gap-3">
                  <input
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    className="min-h-11 flex-1 rounded-[8px] border border-ink/12 bg-white px-4 text-sm text-ink outline-none transition focus:border-tide focus:ring-4 focus:ring-tide/10"
                    placeholder="匿名说点什么..."
                    maxLength={1200}
                  />
                  <button
                    type="submit"
                    className="inline-flex min-h-11 items-center gap-2 rounded-[8px] bg-tide px-4 py-2 text-sm font-medium text-white transition hover:bg-ink"
                  >
                    <Send size={17} />
                    发送
                  </button>
                </div>
              </form>
            </section>
          )}
        </section>

        <aside className="w-full rounded-[8px] border border-white/70 bg-[#fbfaf7]/82 p-5 shadow-calm backdrop-blur lg:w-[320px]">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-ink">情绪聊天室</h2>
            <Users size={18} className="text-moss" />
          </div>
          <div className="mt-4 flex flex-col gap-5">
            {rooms.length === 0 ? (
              <p className="rounded-[8px] border border-dashed border-ink/14 p-4 text-sm leading-6 text-ink/55">
                还没有房间。第一句情绪会生成第一个同频空间。
              </p>
            ) : (
              <>
                <RoomListSection
                  title="我的聊天室"
                  emptyText="匹配进入后，房间会留在这里。"
                  rooms={myRooms}
                  enteringRoomId={enteringRoomId}
                  onRejoin={handleRejoin}
                />
                <RoomListSection title="公共聊天室" rooms={publicRooms} />
              </>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}

function RoomListSection({
  title,
  emptyText,
  rooms,
  enteringRoomId,
  onRejoin
}: {
  title: string;
  emptyText?: string;
  rooms: Room[];
  enteringRoomId?: string | null;
  onRejoin?: (roomId: string) => void;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-ink/68">{title}</h3>
        <span className="text-xs text-ink/42">{rooms.length}</span>
      </div>
      {rooms.length === 0 ? (
        <p className="rounded-[8px] border border-dashed border-ink/14 p-4 text-sm leading-6 text-ink/55">
          {emptyText ?? "只能通过情绪匹配进入公共聊天室。"}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {rooms.map((room) => (
            <div key={room.id} className="rounded-[8px] border border-ink/10 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-ink">{room.name}</div>
                  <div className="mt-1 text-xs text-ink/50">
                    {emotionNames[room.primary_emotion]} · {room.intensity_bucket}
                  </div>
                </div>
                <span className="shrink-0 rounded-[8px] bg-mist px-2 py-1 text-xs text-ink/55">
                  {room.participant_count}
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-ink/52">{room.description}</p>
              {onRejoin ? (
                <button
                  type="button"
                  onClick={() => onRejoin(room.id)}
                  disabled={enteringRoomId === room.id}
                  className="mt-3 inline-flex min-h-9 w-full items-center justify-center gap-2 rounded-[8px] border border-tide/20 bg-mist px-3 py-2 text-xs font-medium text-tide transition hover:border-tide/45 hover:bg-white disabled:cursor-not-allowed disabled:text-tide/45"
                >
                  {enteringRoomId === room.id ? <Loader2 className="animate-spin" size={14} /> : <LogIn size={14} />}
                  回到这个房间
                </button>
              ) : (
                <div className="mt-3 rounded-[8px] bg-[#fbfaf7] px-3 py-2 text-xs leading-5 text-ink/48">
                  通过重新匹配进入
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function CurrentStatusPanel({
  value,
  disabled,
  onChange,
  onSend,
  onDismiss
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="rounded-[8px] border border-tide/18 bg-mist p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-tide">
        <Sparkles size={16} />
        用这句话开场
      </div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-3 min-h-[104px] w-full resize-none rounded-[8px] border border-white bg-white/72 p-3 text-sm leading-6 text-ink outline-none transition focus:border-tide focus:ring-4 focus:ring-tide/10"
        maxLength={180}
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onSend}
          disabled={disabled}
          className="inline-flex min-h-10 items-center gap-2 rounded-[8px] bg-ink px-4 py-2 text-sm font-medium text-white transition hover:bg-tide disabled:cursor-not-allowed disabled:bg-ink/35"
        >
          <Send size={16} />
          发送当前状态
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="inline-flex min-h-10 items-center gap-2 rounded-[8px] border border-ink/10 bg-white px-4 py-2 text-sm text-ink/65 transition hover:border-tide/40 hover:text-ink"
        >
          <Check size={16} />
          暂时不发
        </button>
      </div>
    </div>
  );
}

function EmptyPanel({ loading }: { loading: boolean }) {
  return (
    <div className="flex flex-1 flex-col justify-center rounded-[8px] border border-dashed border-ink/14 bg-[#fbfaf7] p-6">
      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-[8px] bg-mist text-tide">
        {loading ? <Loader2 className="animate-spin" size={20} /> : <Sparkles size={20} />}
      </div>
      <h2 className="text-xl font-semibold text-ink">先让 AI 听懂这一刻</h2>
      <p className="mt-3 text-sm leading-6 text-ink/60">
        系统会识别主情绪、复合情绪、强度和表达意图，再把你放进相近情绪的匿名房间。
      </p>
    </div>
  );
}

function AnalysisPanel({
  analysis,
  onJoin,
  joining
}: {
  analysis: AnalyzeResponse;
  onJoin: () => void;
  joining: boolean;
}) {
  const result = analysis.analysis;
  return (
    <div className="rounded-[8px] border border-tide/18 bg-mist p-5">
      <div className="flex items-center gap-2 text-sm font-medium text-tide">
        <HeartHandshake size={17} />
        AI 理解结果
      </div>
      <h2 className="mt-3 text-2xl font-semibold text-ink">{result.summary_label}</h2>
      <p className="mt-3 text-sm leading-6 text-ink/66">{result.empathy_prompt}</p>
      <div className="mt-5 grid grid-cols-2 gap-3">
        <Metric label="主情绪" value={emotionNames[result.primary_emotion]} />
        <Metric label="强度" value={`${result.intensity}/5`} />
        <Metric label="表达意图" value={intentName(result.share_intent)} />
        <Metric label="情绪倾向" value={result.valence > 0 ? "偏正向" : result.valence < 0 ? "偏低落" : "中性"} />
      </div>
      {result.secondary_emotions.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {result.secondary_emotions.map((item) => (
            <span key={item} className="rounded-[8px] bg-white px-3 py-1.5 text-xs text-ink/62">
              {item}
            </span>
          ))}
        </div>
      ) : null}
      {analysis.recommended_room ? (
        <div className="mt-5 rounded-[8px] border border-white bg-white/72 p-4">
          <div className="text-sm font-medium text-ink">{analysis.recommended_room.name}</div>
          <p className="mt-1 text-sm leading-6 text-ink/58">{analysis.recommended_room.description}</p>
        </div>
      ) : null}
      <button
        type="button"
        onClick={onJoin}
        disabled={joining}
        className="mt-5 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-[8px] bg-ink px-4 py-3 text-sm font-medium text-white transition hover:bg-tide disabled:bg-ink/35"
      >
        {joining ? <Loader2 className="animate-spin" size={17} /> : <MessageCircle size={17} />}
        进入同频房间
      </button>
    </div>
  );
}

function SafetyPanel({ analysis, onReset }: { analysis: AnalyzeResponse; onReset: () => void }) {
  return (
    <div className="rounded-[8px] border border-clay/25 bg-[#fff8f1] p-5">
      <div className="flex items-center gap-2 text-sm font-medium text-clay">
        <Shield size={17} />
        此刻先保证安全
      </div>
      <h2 className="mt-3 text-2xl font-semibold text-ink">{analysis.analysis.summary_label}</h2>
      <p className="mt-3 text-sm leading-6 text-ink/68">{analysis.safety_message}</p>
      <p className="mt-3 text-sm leading-6 text-ink/58">{analysis.analysis.empathy_prompt}</p>
      <button
        type="button"
        onClick={onReset}
        className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-[8px] bg-clay px-4 py-3 text-sm font-medium text-white transition hover:bg-ink"
      >
        <RefreshCcw size={17} />
        回到输入
      </button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-white bg-white/76 p-3">
      <div className="text-xs text-ink/45">{label}</div>
      <div className="mt-1 text-sm font-medium text-ink">{value}</div>
    </div>
  );
}

function intentName(intent: string) {
  return (
    {
      celebrate: "想分享",
      vent: "想发泄",
      seek_comfort: "想被安慰",
      listen: "想倾听",
      reflect: "想整理"
    }[intent] ?? "想表达"
  );
}
