from NodeGraphQt import BaseNode, NodeBaseWidget
from PySide2 import QtWidgets, QtCore


# ============================================
# AI 학습용 노하우 구조화 도구 - 노드 정의
# ============================================

# [추가] 여러 줄 텍스트 입력 위젯 정의
class MultiLineTextWidget(NodeBaseWidget):
    def __init__(self, parent=None, name=None, label='정보 수집 설명'):
        # parent는 None으로 설정 (NodeGraphQt가 자동으로 처리)
        # label이 제공되지 않으면 기본값 '정보 수집 설명' 사용
        if not label:
            label = '정보 수집 설명'
        super(MultiLineTextWidget, self).__init__(parent=None, name=name, label=label)
        
        # 1. Qt의 QTextEdit 생성 (여러 줄 입력 가능)
        self._text_edit = QtWidgets.QTextEdit()
        
        # 2. 스타일 조정
        self._text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #3e3e3e;
                color: #eeeeee;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px;
                min-height: 80px;
                font-size: 9px;
            }
        """)
        
        # 3. 위젯 등록
        self.set_custom_widget(self._text_edit)
        
        # 4. 값 변경 감지 연결
        self._text_edit.textChanged.connect(self.on_value_changed)

    def get_value(self):
        """현재 입력된 텍스트 반환"""
        return self._text_edit.toPlainText()

    def set_value(self, value):
        """값 설정 (텍스트로 설정)"""
        if value:
            self._text_edit.setPlainText(str(value))
        else:
            self._text_edit.clear()

# [추가] 직접 입력과 선택이 모두 가능한 콤보박스 위젯 정의
class EditableComboWidget(NodeBaseWidget):
    def __init__(self, parent=None, name=None, label='', items=None):
        # parent는 None으로 설정 (NodeGraphQt가 자동으로 처리)
        super(EditableComboWidget, self).__init__(parent=None, name=name, label=label)
        
        # 1. Qt의 기본 콤보박스 생성
        self._combo = QtWidgets.QComboBox()
        
        # 2. 핵심! 편집 가능하도록 설정 (이게 있어야 타이핑이 됩니다)
        self._combo.setEditable(True)
        
        # 3. 아이템 추가
        if items:
            self._combo.addItems(items)
            
        # 4. 스타일 조정 (선택 사항)
        self._combo.setStyleSheet("""
            QComboBox {
                background-color: #3e3e3e;
                color: #eeeeee;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 2px;
                font-size: 9px;
            }
            QComboBox:on { /* 팝업이 열렸을 때 */
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #4e4e4e;
                color: #eeeeee;
                selection-background-color: #5e5e5e;
                font-size: 9px;
            }
        """)

        # 5. 위젯 등록
        self.set_custom_widget(self._combo)
        
        # 6. 값 변경 감지 연결
        self._combo.editTextChanged.connect(self.on_value_changed)
        self._combo.currentIndexChanged.connect(self.on_value_changed)

    def get_value(self):
        """현재 입력된 텍스트(또는 선택된 텍스트) 반환"""
        return self._combo.currentText()

    def set_value(self, value):
        """값 설정 (텍스트로 설정)"""
        if value:
            self._combo.setCurrentText(str(value))

# 0. 상황 트리거 노드 (Trigger Source Node) - 트리거 소스
class TriggerSourceNode(BaseNode):
    """
    상황 트리거 소스 노드 - 메일, 메신저, 이상감지 등
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = '시작'

    def __init__(self):
        super(TriggerSourceNode, self).__init__()
        
        # 밝은 초록색 계열 - 트리거 소스
        self.set_color(50, 150, 50)
        
        # 출력만 있음 (상황 노드의 입력에 연결)
        self.add_output('상황')
        
        # 트리거 소스 선택
        trigger_sources = ['메일', '메신저', '이상감지']
        self.add_combo_menu('trigger_source', '트리거 소스', items=trigger_sources)
        if trigger_sources:
            self.set_property('trigger_source', trigger_sources[0])  # 기본값은 첫 번째 항목
        
        # 비고 텍스트 입력
        self.add_text_input('note', '비고')
        self.set_property('note', '')  # 기본값은 빈 문자열
        
        # 파일 첨부 속성은 노드 생성 후 main.py에서 동적으로 추가됨

# 1. 상황 노드 (Trigger Node) - 분석 시작점
class TriggerNode(BaseNode):
    """
    AI 학습 포인트: "이런 문제가 발생했을 때 분석을 시작해라"
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = '상황'

    def __init__(self):
        super(TriggerNode, self).__init__()
        
        # 초록색 계열 - 시작점을 나타냄
        self.set_color(20, 100, 50)
        
        # 입력: 상황 트리거 소스에서 연결
        self.add_input('트리거', multi_input=True)
        # 출력: 분석 시작
        self.add_output('시작')
        
        # 상황 설명 입력
        self.add_text_input('situation', '상황 설명')
        
        # 상황 유형 선택 (JSON 파일에서 로드)
        import json
        import os
        
        def load_situation_types_from_json():
            """JSON 파일에서 상황 유형 목록 로드"""
            try:
                json_path = os.path.join(os.path.dirname(__file__), 'situation_types.json')
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('situation_types', [])
            except FileNotFoundError:
                # 파일이 없으면 기본 목록 반환
                return ['반송 지연', '설비 오류', '재고 불일치', '센서 이상', '통신 장애', '기타']
            except Exception as e:
                print(f"⚠️ 상황 유형 목록 로드 실패: {e}")
                return ['반송 지연', '설비 오류', '재고 불일치', '센서 이상', '통신 장애', '기타']
        
        situation_types = load_situation_types_from_json()
        self.add_combo_menu('situation_type', '상황 유형', items=situation_types)
        if situation_types:
            self.set_property('situation_type', situation_types[0])  # 기본값은 첫 번째 항목
        
        # 파일 첨부 속성은 노드 생성 후 main.py에서 동적으로 추가됨


# 2. 정보 수집 노드 (Data Gathering Node) - 설명만 담는 노드
class DataQueryNode(BaseNode):
    """
    AI 학습 포인트: "문제를 풀려면 이 데이터를 먼저 찾아봐야 해" (Tool Usage 능력 학습)
    이 노드는 정보 수집에 대한 설명만 담고, 실제 데이터 소스는 별도 노드(테이블, 화면, 로그)에 연결
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = '정보 수집 (Data Gathering)'

    def __init__(self): 
        super(DataQueryNode, self).__init__()
        
        # 파란색 계열 - 데이터 관련
        self.set_color(10, 50, 80)
        
        # 입력과 출력 포트
        # multi_input=True로 설정하여 여러 노드의 출력을 하나의 입력에 연결 가능
        self.add_input('이전 단계', multi_input=True)
        # 데이터(List) 입력에 여러 데이터 소스 노드들(테이블, 화면, 로그)을 연결 가능
        self.add_input('데이터(List)', multi_input=True)
        self.add_output('다음 단계')
        
        # 정보 수집에 대한 설명만 입력 (여러 줄 입력 가능)
        # 일단 add_text_input을 사용하고, 나중에 main.py에서 위젯을 교체
        self.add_text_input('description', '정보 수집 설명')
        self.set_property('description', '수집할 정보를 설명하세요 (예: 반송 지연 관련 데이터 수집)')
        
        # 파일 첨부 속성은 노드 생성 후 main.py에서 동적으로 추가됨

# 2-1. 테이블 노드 (Table Node) - 실제 테이블 데이터 소스
class TableNode(BaseNode):
    """
    테이블 데이터 소스 노드
    정보 수집 노드의 데이터(List) 출력에 연결
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = 'DB 테이블'

    def __init__(self): 
        super(TableNode, self).__init__()
        
        # 청록색 계열 - 테이블 데이터
        self.set_color(10, 150, 100)
        
        # 입력 포트 추가 (다른 테이블로부터 만들어질 수 있으므로)
        self.add_input('입력 테이블', multi_input=True)
        
        # 출력 (정보 수집 노드의 데이터(List)에 연결)
        self.add_output('테이블 데이터')
        
        # 테이블 선택 (JSON 파일에서 로드)
        import json
        import os
        
        def load_tables_from_json():
            """JSON 파일에서 테이블 목록 로드"""
            try:
                json_path = os.path.join(os.path.dirname(__file__), 'tables.json')
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('tables', [])
            except FileNotFoundError:
                # 파일이 없으면 기본 목록 반환
                return ['TB_MCS_LOG', 'TB_WMS_STOCK', 'TB_OHT_STATUS', 'TB_EQP_ALARM', 'TB_TRANSPORT', 'TB_SENSOR']
            except Exception as e:
                print(f"⚠️ 테이블 목록 로드 실패: {e}")
                return ['TB_MCS_LOG', 'TB_WMS_STOCK', 'TB_OHT_STATUS', 'TB_EQP_ALARM', 'TB_TRANSPORT', 'TB_SENSOR']
        
        tables = load_tables_from_json()
        self.add_combo_menu('target_table', '대상 테이블', items=tables)
        if tables:
            self.set_property('target_table', tables[0])  # 기본값은 첫 번째 항목
        
        # 확인할 컬럼들 (여러 개 선택 가능)
        # 쉼표로 구분하여 여러 컬럼 입력 (예: Error_Code, Transport_ID, Lot_ID)
        try:
            # placeholder 파라미터가 있는지 확인
            self.add_text_input('target_columns', '확인 컬럼', placeholder='예: Error_Code, Transport_ID, Lot_ID')
        except TypeError:
            # placeholder가 지원되지 않으면 기본 방법 사용
            self.add_text_input('target_columns', '확인 컬럼')
        self.set_property('target_columns', '예: A,B,C..')  # 기본값
        
        # 파일 첨부 속성은 노드 생성 후 main.py에서 동적으로 추가됨

# 2-2. 화면 노드 (Screen Node) - 화면 데이터 소스
class ScreenNode(BaseNode):
    """
    화면 데이터 소스 노드
    정보 수집 노드의 데이터(List) 출력에 연결
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = '화면 (Screen)'

    def __init__(self): 
        super(ScreenNode, self).__init__()
        
        # 보라색 계열 - 화면 데이터
        self.set_color(150, 50, 150)
        
        # 입력 포트 추가 (다른 소스로부터 만들어질 수 있으므로)
        self.add_input('입력 데이터', multi_input=True)
        
        # 출력 (정보 수집 노드의 데이터(List)에 연결)
        self.add_output('화면 데이터')
        
        # 화면 선택 (JSON 파일에서 로드)
        import json
        import os
        
        def load_screens_from_json():
            """JSON 파일에서 화면 목록 로드"""
            try:
                json_path = os.path.join(os.path.dirname(__file__), 'screens.json')
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('screens', [])
            except FileNotFoundError:
                # 파일이 없으면 기본 목록 반환
                return ['반송 현황 화면', '설비 상태 화면', '재고 관리 화면', '알람 모니터링 화면', '센서 데이터 화면']
            except Exception as e:
                print(f"⚠️ 화면 목록 로드 실패: {e}")
                return ['반송 현황 화면', '설비 상태 화면', '재고 관리 화면', '알람 모니터링 화면', '센서 데이터 화면']
        
        screens = load_screens_from_json()
        self.add_combo_menu('screen_name', '화면명', items=screens)
        if screens:
            self.set_property('screen_name', screens[0])  # 기본값은 첫 번째 항목
        
        self.add_text_input('screen_url', '화면 URL/경로')
        self.set_property('screen_url', '화면 경로를 입력하세요')
        
        self.add_text_input('screen_elements', '확인 요소')
        self.set_property('screen_elements', '확인할 화면 요소를 입력하세요 (예: 버튼, 텍스트, 상태)')

# 2-3. SQL 노드 (SQL Node) - SQL 쿼리 데이터 소스
class SQLNode(BaseNode):
    """
    SQL 쿼리 데이터 소스 노드
    정보 수집 노드의 데이터(List) 출력에 연결
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = 'SQL'

    def __init__(self): 
        super(SQLNode, self).__init__()
        
        # 노란색 계열 - SQL 데이터
        self.set_color(200, 150, 50)
        
        # 입력 포트 추가 (다른 테이블로부터 만들어질 수 있으므로)
        self.add_input('입력 테이블', multi_input=True)
        
        # 출력 (정보 수집 노드의 데이터(List)에 연결)
        self.add_output('SQL 데이터')
        
        # SQL 쿼리 입력
        self.add_text_input('sql_query', 'SQL 쿼리')
        self.set_property('sql_query', 'SELECT * FROM table_name WHERE condition')
        
        # SQL 설명 (선택 사항)
        self.add_text_input('sql_description', 'SQL 설명')
        self.set_property('sql_description', '이 SQL 쿼리의 목적을 설명하세요')
        
        # 파일 첨부 속성은 노드 생성 후 main.py에서 동적으로 추가됨

# 2-4. 로그 노드 (Log Node) - 로그 데이터 소스
class LogNode(BaseNode):
    """
    로그 데이터 소스 노드
    정보 수집 노드의 데이터(List) 출력에 연결
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = '로그 (Log)'

    def __init__(self): 
        super(LogNode, self).__init__()
        
        # 주황색 계열 - 로그 데이터
        self.set_color(200, 100, 50)
        
        # 입력 포트 추가 (다른 소스로부터 만들어질 수 있으므로)
        self.add_input('입력 데이터', multi_input=True)
        
        # 출력 (정보 수집 노드의 데이터(List)에 연결)
        self.add_output('로그 데이터')
        
        # 로그 소스 선택 (JSON 파일에서 로드)
        import json
        import os
        
        def load_logs_from_json():
            """JSON 파일에서 로그 목록 로드"""
            try:
                json_path = os.path.join(os.path.dirname(__file__), 'logs.json')
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('logs', [])
            except FileNotFoundError:
                # 파일이 없으면 기본 목록 반환
                return ['MCS 로그', '시스템 로그', '애플리케이션 로그', '에러 로그', '접근 로그']
            except Exception as e:
                print(f"⚠️ 로그 목록 로드 실패: {e}")
                return ['MCS 로그', '시스템 로그', '애플리케이션 로그', '에러 로그', '접근 로그']
        
        logs = load_logs_from_json()
        self.add_combo_menu('log_source', '로그 소스', items=logs)
        if logs:
            self.set_property('log_source', logs[0])  # 기본값은 첫 번째 항목
        
        self.add_text_input('log_path', '로그 경로')
        self.set_property('log_path', '로그 파일 경로를 입력하세요')
        
        self.add_text_input('log_pattern', '로그 패턴/키워드')
        self.set_property('log_pattern', '찾을 로그 패턴이나 키워드를 입력하세요')
        
        # 파일 첨부 속성은 노드 생성 후 main.py에서 동적으로 추가됨


# 3. 판단 노드 (Decision Node) - Chain of Thought 핵심
class DecisionNode(BaseNode):
    """
    AI 학습 포인트: Chain of Thought (생각의 사슬)를 가르치는 핵심 구간
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = '판단 (Decision)'

    def __init__(self):
        super(DecisionNode, self).__init__()
        
        # 붉은 계열 - 판단/분기점
        self.set_color(80, 20, 20)
        
        # multi_input=True로 설정하여 여러 노드의 출력을 하나의 입력에 연결 가능
        self.add_input('데이터 입력', multi_input=True)
        
        # Yes / No 분기
        self.add_output('True (참)')
        self.add_output('False (거짓)')
        
        # 판단 조건 (논리식)
        self.add_text_input('condition', '판단 조건')
        
        # 판단 근거 설명 (AI에게 왜 이렇게 판단하는지 가르침)
        self.add_text_input('reasoning', '판단 근거')
        
        # 파일 첨부 속성은 노드 생성 후 main.py에서 동적으로 추가됨


# 4. 반복/범위 노드 (Loop Node)
class LoopNode(BaseNode):
    """
    AI 학습 포인트: "하나만 보지 말고, 리스트 전체를 훑어서 패턴을 찾아"
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = '반복 (Loop)'

    def __init__(self):
        super(LoopNode, self).__init__()
        
        # 보라색 계열 - 반복/그룹
        self.set_color(100, 50, 150)
        
        # multi_input=True로 설정하여 여러 노드의 출력을 하나의 입력에 연결 가능
        self.add_input('반복 대상 리스트', multi_input=True)
        
        # 반복 내부로 들어가는 포트와 반복 종료 시 나가는 포트
        self.add_output('반복 시작')
        self.add_output('반복 종료 시')
        
        # 반복 대상 설명
        self.add_text_input('target', '반복 대상')
        
        # 반복 종료 조건
        self.add_text_input('exit_condition', '반복 종료 조건')
        
        # 파일 첨부 속성은 노드 생성 후 main.py에서 동적으로 추가됨


# 5. 결론 노드 (Conclusion Node) - 분석 결과
class ConclusionNode(BaseNode):
    """
    AI 학습 포인트: 최종 결론을 명확하게 정리
    """
    __identifier__ = 'com.samsung.logistics'
    NODE_NAME = '결론 (Conclusion)'

    def __init__(self):
        super(ConclusionNode, self).__init__()
        
        # 주황색 계열 - 결론/종료
        self.set_color(200, 120, 50)
        
        # multi_input=True로 설정하여 여러 노드의 출력을 하나의 입력에 연결 가능
        self.add_input('입력', multi_input=True)
        
        # 결론 내용
        self.add_text_input('conclusion', '결론 내용')
        
        # 결론 유형
        conclusion_types = [
            '원인 파악',
            '조치 사항',
            '예방 방안',
            '기타'
        ]
        self.add_combo_menu('conclusion_type', '결론 유형', items=conclusion_types)
        if conclusion_types:
            self.set_property('conclusion_type', conclusion_types[0])  # 기본값은 첫 번째 항목
        
        # 파일 첨부 속성 (숨김 속성으로 저장)
        self.set_property('attached_file', '')