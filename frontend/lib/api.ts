const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8058";

export type Session = {
  session_id: string;
  display_name: string;
};

export type EmotionAnalysis = {
  primary_emotion:
    | "joy"
    | "sadness"
    | "anxiety"
    | "anger"
    | "loneliness"
    | "stress"
    | "gratitude"
    | "shame"
    | "confusion"
    | "neutral";
  secondary_emotions: string[];
  intensity: number;
  valence: number;
  arousal: number;
  share_intent: "celebrate" | "vent" | "seek_comfort" | "listen" | "reflect";
  summary_label: string;
  safety_risk: "none" | "self_harm" | "violence" | "severe_distress";
  empathy_prompt: string;
  status_message: string;
};

export type Room = {
  id: string;
  primary_emotion: EmotionAnalysis["primary_emotion"];
  intensity_bucket: string;
  name: string;
  description: string;
  online_count: number;
  participant_count: number;
  joined_by_me: boolean;
};

export type AnalyzeResponse = {
  analysis_id: string;
  analysis: EmotionAnalysis;
  recommended_room: Room | null;
  safe_to_join: boolean;
  safety_message: string | null;
};

export type Message = {
  id: string;
  room_id: string;
  session_id: string;
  display_name: string;
  content: string;
  safety_status: string;
  created_at: string;
};

export type JoinRoomResponse = {
  room: Room;
  messages: Message[];
  ws_url: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? "请求失败，请稍后再试。");
  }

  return response.json() as Promise<T>;
}

export function createSession() {
  return request<Session>("/api/sessions", { method: "POST" });
}

export function analyzeEmotion(sessionId: string, text: string) {
  return request<AnalyzeResponse>("/api/emotions/analyze", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, text })
  });
}

export function joinRoom(sessionId: string, analysisId: string) {
  return request<JoinRoomResponse>("/api/rooms/join", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, analysis_id: analysisId })
  });
}

export function rejoinRoom(sessionId: string, roomId: string) {
  return request<JoinRoomResponse>("/api/rooms/rejoin", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, room_id: roomId })
  });
}

export function listRooms(sessionId?: string) {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return request<Room[]>(`/api/rooms${query}`);
}
