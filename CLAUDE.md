# CLAUDE.md — lotto_number repo

## 프로젝트 구조

이 레포지토리는 한국 로또 6/45 분석/추천 시스템입니다.

```
lotto_number/
└── lotto-doctor/          ← 메인 프로젝트 (여기서 작업)
    ├── src/lotto_doctor/  ← 패키지 소스
    ├── tests/             ← 테스트
    ├── data/lotto.db      ← SQLite DB (1~1229회차)
    ├── config/            ← YAML 설정
    ├── .github/workflows/ ← GitHub Actions
    └── CLAUDE.md          ← 상세 개발 가이드
```

**작업 시 반드시 `lotto-doctor/` 디렉토리로 이동 후 진행.**

## 브랜치

- 기본 브랜치: `claude/intelligent-dijkstra-c4lpeh`

## 빠른 시작

```bash
cd lotto-doctor
pip install -e ".[dev]"      # Python 3.10+ 지원
lotto-doctor collect --source github   # 데이터 수집 (GitHub 소스 사용)
lotto-doctor analyze
lotto-doctor recommend
```

## 데이터 수집 주의사항

`dhlottery.co.kr` API는 RSA 봇 차단으로 접근 불가.
**반드시 `--source github` 옵션 사용** (smok95/lotto GitHub 레포 기반).

```bash
lotto-doctor collect --source github   # 기본값, 항상 이걸 사용
lotto-doctor collect --source api      # 사용 불가 (차단됨)
```

## 서버 정보

- Ubuntu 서버: `ubuntu@168.107.4.184`
- SSH 키: `C:\Users\rmsdu\Desktop\ssh-key-2026-04-17.key` (로컬 PC)
- 서버 원격 명령: GitHub Actions → `Server Deploy / Command` 워크플로우

## GitHub Secrets (등록 완료)

| Secret | 용도 |
|--------|------|
| `SSH_PRIVATE_KEY` | 서버 SSH 접속 |
| `SSH_HOST` | 서버 IP |
| `SSH_USER` | 서버 계정 |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 |
| `TELEGRAM_CHAT_ID` | 텔레그램 채널 |

## 상세 개발 가이드

→ `lotto-doctor/CLAUDE.md` 참조
