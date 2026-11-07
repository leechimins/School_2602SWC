"""외부 연동 — 구글 캘린더(에브리타임은 논의 중). 레인 B.

- google_calendar.py: 구글 호출이 일어나는 유일한 곳
- service.py: 약속 → "바쁨" 변환, 연결·동기화·끊기
- router.py: /me/integrations/*
- 연결 상태 테이블(CalendarLink)은 다른 B 테이블과 함께 minutes/models.py에 있다
"""
