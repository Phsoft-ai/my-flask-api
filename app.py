import time
import datetime
import requests
from bs4 import BeautifulSoup
import re
from flask import Flask, request, jsonify
import pytz # 시간대 처리를 위해 pytz 라이브러리 추가

app = Flask(__name__)

# --- 기존에 제공해주신 함수들 (수정 없이 유지) ---

def get_qt_schedule(year, month):
    """
    두란노 QT 캘린더 API를 사용하여 특정 달의 QT 스케줄 데이터를 가져옵니다.
    Args:
      year: 년도 (YYYY 형식)
      month: 월 (MM 형식, 1-12)
    Returns:
      스케줄 데이터 리스트. 각 스케줄 데이터는 딕셔너리 형태로, 다음 키를 가집니다:
        - day: 일
        - bible: 성경 범위
        - week: 요일 (리스트 뷰에서 가져옴)
        - title: 제목 (리스트 뷰에서 가져옴)
      에러 발생시 None을 반환합니다.
    """
    month_str = f"{month:02d}"  # API는 MM 형식을 기대
    url = f"https://www.duranno.com/qt/view/calendar2.asp?onDate={year}-{month_str}"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {url}: {e}")
        return None

    soup = BeautifulSoup(response.content, "html.parser")
    schedule_data = {}

    # 1. 테이블 방식 파싱 (기본 날짜와 성경 범위)
    table_view = soup.find('div', class_='calendar-table')
    if table_view:
        for row in table_view.find_all('tr')[1:]:
            for cell in row.find_all('td'):
                d = cell.find('span', class_='day')
                b = cell.find('span', class_='bible')
                if d and b:
                    day = d.text.strip()
                    bible = b.text.strip().replace('\xa0', ' ')
                    if day:
                        schedule_data[day] = {'day':day,'bible':bible,'week':None,'title':None}

    # 2. 리스트 방식 파싱 (요일, 제목 정보 및 성경 범위 보충)
    list_view = soup.find('div', class_='calendar-list')
    if list_view:
        for tr in list_view.find_all('tr', class_=lambda x: x and 'person' in x.split()):
            t = tr.find('td', class_='time')
            n = tr.find('td', class_='name')
            ti = tr.find('td', class_='title')
            v = tr.find('td', class_='views')
            if t and n and ti and v:
                day = t.find('span').text.strip()
                week = n.find('span').text.strip()
                title = ti.find('span').text.strip()
                bible = v.text.strip().replace('\xa0', ' ')
                schedule_data[day] = {'day':day,'bible':bible,'week':week,'title':title}

    return sorted(schedule_data.values(), key=lambda x: int(x['day']))


def parse_bible_text(bible_text_input):
    """
    성경 구절 텍스트를 파싱하여 JSON 형식으로 변환합니다.
    교차 장 범위를 두 개의 개별 구절로 분리합니다.
    예: "민수기 23:27~24:9" → 두 개의 dict: 23장 27절, 24장 9절
    """
    book_mapping = {
        '창세기':1, '출애굽기':2, '레위기':3, '민수기':4, '신명기':5, '여호수아':6, '사사기':7, '룻기':8, '사무엘상':9, '사무엘하':10,
        '열왕기상':11, '열왕기하':12, '역대상':13, '역대하':14, '에스라':15, '느헤미야':16, '에스더':17, '욥기':18, '시편':19, '잠언':20,
        '전도서':21, '아가':22, '이사야':23, '예레미야':24, '예레미야애가':25, '에스겔':26, '다니엘':27, '호세아':28, '요엘':29, '아모스':30,
        '오바댜':31, '요나':32, '미가':33, '나훔':34, '하박국':35, '스바냐':36, '학개':37, '스가랴':38, '말라기':39, '마태복음':40,
        '마가복음':41, '누가복음':42, '요한복음':43, '사도행전':44, '로마서':45, '고린도전서':46, '고린도후서':47, '갈라디아서':48, '에베소서':49, '빌립보서':50,
        '골로새서':51, '데살로니가전서':52, '데살로니가후서':53, '디모데전서':54, '디모데후서':55, '디도서':56, '빌레몬서':57, '히브리서':58, '야고보서':59, '베드로전서':60,
        '베드로후서':61, '요한일서':62, '요한이서':63, '요한삼서':64, '유다서':65, '요한계시록':66
    }
    results = []
    # 패턴: 책 이름, 장:시작절, 범위(~ or -), 선택적 장:끝절 or 끝절
    # 단일 구절 (예: 시편 1:1) 처리 추가
    pattern_range = re.compile(r"([가-힣]+[0-9]*서?)\s*(\d+):(\d+)[~-](?:(\d+):)?(\d+)")
    pattern_single = re.compile(r"([가-힣]+[0-9]*서?)\s*(\d+):(\d+)")

    # 범위 구절 먼저 시도
    for m in pattern_range.finditer(bible_text_input):
        book_raw = m.group(1)
        start_ch = int(m.group(2))
        start_vs = int(m.group(3))
        if m.group(4):
            end_ch = int(m.group(4))
        else:
            end_ch = start_ch
        end_vs = int(m.group(5))
        
        bk = book_mapping.get(book_raw)
        if not bk: # 일서, 이서, 삼서 등 처리
            bk = book_mapping.get(book_raw.replace('일서','1서').replace('이서','2서').replace('삼서','3서'))
        if not bk:
            print(f"Warning: Unknown book '{book_raw}' in range parsing")
            continue

        if start_ch != end_ch:
            results.append({'book':bk,'chapter':start_ch,'start':start_vs,'end':start_vs})
            results.append({'book':bk,'chapter':end_ch,'start':end_vs,'end':end_vs})
        else:
            results.append({'book':bk,'chapter':start_ch,'start':start_vs,'end':end_vs})
        return results # 파싱 성공 시 바로 반환

    # 단일 구절 시도
    for m in pattern_single.finditer(bible_text_input):
        book_raw = m.group(1)
        chapter = int(m.group(2))
        verse = int(m.group(3))
        
        bk = book_mapping.get(book_raw)
        if not bk: # 일서, 이서, 삼서 등 처리
            bk = book_mapping.get(book_raw.replace('일서','1서').replace('이서','2서').replace('삼서','3서'))
        if not bk:
            print(f"Warning: Unknown book '{book_raw}' in single parsing")
            continue
        
        results.append({'book':bk,'chapter':chapter,'start':verse,'end':verse})
        return results # 파싱 성공 시 바로 반환

    if not results and bible_text_input.strip():
        print(f"Warning: Failed to parse '{bible_text_input}'")
    return results

# --- timestamp_to_qt_data_ms 함수 수정 ---
def timestamp_to_qt_data_ms(timestamp_ms, timezone_str='Asia/Seoul'):
    """
    밀리초 단위 타임스탬프와 시간대 문자열을 받아 QT 구절 파싱 결과를 반환합니다.
    Args:
        timestamp_ms (int): 밀리초 단위의 타임스탬프 (UTC 기준).
        timezone_str (str): 원하는 시간대 문자열 (예: 'Asia/Seoul', 'America/New_York').
                            **기본값은 'Asia/Seoul' (한국 표준시)입니다.**
    Returns:
        list: 파싱된 성경 구절 데이터 리스트. 에러 발생 시 빈 리스트.
    """
    try:
        # UTC 타임스탬프를 UTC datetime 객체로 변환
        dt_utc = datetime.datetime.fromtimestamp(timestamp_ms / 1000, tz=pytz.utc)

        # 지정된 시간대 객체 가져오기
        target_timezone = pytz.timezone(timezone_str)

        # UTC datetime 객체를 지정된 시간대로 변환
        dt_localized = dt_utc.astimezone(target_timezone)
        
        # 변환된 날짜의 연, 월, 일을 추출하여 QT 스케줄 가져오기
        sched = get_qt_schedule(dt_localized.year, dt_localized.month)
        if not sched:
            return []
        
        # 해당 날짜의 성경 본문 찾기
        bible = next((i['bible'] for i in sched if int(i['day']) == dt_localized.day), None)
        
        return parse_bible_text(bible) if bible else []

    except pytz.exceptions.UnknownTimeZoneError:
        print(f"Error: Unknown timezone '{timezone_str}'")
        return []
    except Exception as e:
        print(f"An unexpected error occurred in timestamp_to_qt_data_ms: {e}")
        return []

# --- API 엔드포인트 정의 ---
@app.route('/get-qt-bible-data', methods=['GET'])
def get_qt_bible_data():
    """
    쿼리 파라미터로 밀리초 단위 타임스탬프와 시간대 문자열을 받아 QT 성경 구절 데이터를 반환합니다.
    **'timezone' 파라미터가 제공되지 않으면 기본적으로 'Asia/Seoul' (한국 시간)을 사용합니다.**
    예시:
    - 한국 시간 (기본값 사용): /get-qt-bible-data?timestamp_ms=1747551764480
    - 한국 시간 (명시적 지정): /get-qt-bible-data?timestamp_ms=1747551764480&timezone=Asia/Seoul
    - 뉴욕 시간: /get-qt-bible-data?timestamp_ms=1747551764480&timezone=America/New_York
    """
    timestamp_ms_str = request.args.get('timestamp_ms')
    # 기본값을 'Asia/Seoul'로 설정하여 한국 시간으로 동작하도록 함
    timezone_str = request.args.get('timezone', 'Asia/Seoul') 

    if not timestamp_ms_str:
        return jsonify({"error": "timestamp_ms parameter is required"}), 400
    
    try:
        timestamp_ms = int(timestamp_ms_str)
    except ValueError:
        return jsonify({"error": "Invalid timestamp_ms format. Must be an integer."}), 400

    try:
        # pytz가 인식하는 유효한 시간대인지 먼저 확인
        pytz.timezone(timezone_str)
    except pytz.exceptions.UnknownTimeZoneError:
        return jsonify({"error": f"Invalid timezone: '{timezone_str}'. Please provide a valid IANA timezone string (e.g., 'Asia/Seoul', 'America/New_York')."}), 400

    qt_data = timestamp_to_qt_data_ms(timestamp_ms, timezone_str)
    
    if not qt_data and timestamp_ms_str: # 데이터가 없지만 입력은 유효한 경우 (예: 해당 날짜의 QT 본문이 없는 경우)
        return jsonify({"message": "No QT data found for the given timestamp and timezone, or parsing failed.", "data": []})

    return jsonify(qt_data)

# Leapcell에서 실행될 때 필요한 설정 (디버그 모드 아님)
if __name__ == '__main__':
    # 로컬에서 테스트할 때는 아래 주석을 해제하고 실행합니다.
    # app.run(debug=True, port=5000)
    pass # Leapcell은 gunicorn 등으로 앱을 실행합니다.
