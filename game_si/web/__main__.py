"""Run only on loopback: python -m game_si.web."""
import argparse
import socket


def main():
    parser = argparse.ArgumentParser(description='게임 소스 분석 웹 프로그램 (본인 PC 전용)')
    parser.add_argument('--port', type=int, default=8765, help='로컬 접속 포트 (기본 8765)')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('포트는 1024~65535 사이로 지정해 주세요.')
    try:
        import uvicorn
        from .app import create_app
    except ImportError:
        parser.exit(1, '웹 실행 의존성이 필요합니다: py -3.10 -m pip install -e ".[web]"\n')
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', args.port))
    except OSError:
        parser.exit(1, f'{args.port} 포트를 사용할 수 없습니다. --port로 다른 포트를 선택해 주세요.\n')
    print(f'브라우저에서 http://127.0.0.1:{args.port} 에 접속해 주세요. 종료: Ctrl+C', flush=True)
    uvicorn.run(create_app(), host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
