from typing import Dict, List
from fastapi import WebSocket

class ConnectionManager:
    """사용자별 웹소켓 연결을 관리하는 클래스"""
    def __init__(self):
        # {user_id: [websocket1, websocket2, ...]}
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"[WS] User {user_id} connected. Active sessions: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            except ValueError:
                pass

    async def broadcast(self, user_id: str, message: str):
        """특정 사용자에게 메시지 전송 (모든 기기)"""
        if user_id in self.active_connections:
            # 연결이 끊긴 소켓이 있을 수 있으므로 복사본으로 순회
            for connection in list(self.active_connections[user_id]):
                try:
                    await connection.send_text(message)
                except Exception:
                    self.disconnect(user_id, connection)

manager = ConnectionManager()