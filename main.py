import sys
import json
import os
import shutil
import zipfile
import tempfile
import atexit
import uuid
from pathlib import Path
from PySide2 import QtWidgets, QtCore, QtGui
from NodeGraphQt import NodeGraph

# NodeTreeWidget은 선택적 (버전에 따라 없을 수 있음)
try:
    from NodeGraphQt import NodeTreeWidget
    HAS_NODE_TREE = True
except ImportError:
    HAS_NODE_TREE = False
    print("[WARNING] NodeTreeWidget을 사용할 수 없습니다. 그래프 영역에서 우클릭하여 노드를 추가하세요.")

# 우리가 만든 노드 파일 불러오기
from nodes import (
    TriggerSourceNode,
    TriggerNode,
    DataQueryNode,
    TableNode,
    ScreenNode,
    SQLNode,
    LogNode,
    DecisionNode,
    LoopNode,
    ConclusionNode
)


def ensure_attached_file_property(node):
    """Ensure node has a proper attached_file property."""
    if not node:
        return False
    try:
        node.get_property('attached_file')
        return True
    except Exception:
        pass
    try:
        if hasattr(node, 'create_property'):
            node.create_property('attached_file', '', widget_type=None)
        elif hasattr(node, 'model') and hasattr(node.model, 'set_property'):
            node.model.set_property('attached_file', '')
        elif hasattr(node, '_properties'):
            node._properties['attached_file'] = ''
        return True
    except Exception as e:
        print(f"⚠️ attached_file 속성 생성 실패: {e}")
        return False


def set_attached_file(node, value):
    """Set attached file path on node (property + fallback attribute)."""
    if not node:
        return
    value = value or ''

    try:
        path_obj = Path(value)
        if path_obj.is_absolute() and path_obj.exists():
            unique_name = f"{path_obj.stem}_{uuid.uuid4().hex[:8]}{path_obj.suffix}"
            dest_path = attachments_dir / unique_name
            shutil.copy2(path_obj, dest_path)
            value = (ATTACHMENTS_VIRTUAL_ROOT / dest_path.name).as_posix()
    except Exception as e:
        print(f"⚠️ 첨부 파일 복사 실패: {e}")

    ensure_attached_file_property(node)
    try:
        node.set_property('attached_file', value)
    except Exception as e:
        print(f"⚠️ attached_file 속성 설정 실패: {e}")
    setattr(node, '_attached_file_path', value)


def get_attached_file(node):
    """Get attached file path from node (property or fallback attribute)."""
    if not node:
        return ''
    ensure_attached_file_property(node)
    try:
        value = node.get_property('attached_file')
        if isinstance(value, str):
            if value:
                setattr(node, '_attached_file_path', value)
            return value if value else getattr(node, '_attached_file_path', '')
    except Exception:
        pass
    return getattr(node, '_attached_file_path', '')


ATTACHMENTS_VIRTUAL_ROOT = Path('attachments')
attachments_dir = Path(tempfile.mkdtemp(prefix='sdc_logiccanvas_attachments_'))
print(f"✅ 임시 첨부 폴더 준비 완료: {attachments_dir}")


def clear_attachments_dir():
    """임시 첨부 폴더 비우기."""
    try:
        attachments_dir.mkdir(parents=True, exist_ok=True)
        for child in attachments_dir.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
            else:
                shutil.rmtree(child, ignore_errors=True)
    except Exception as e:
        print(f"⚠️ 첨부 폴더 정리 실패: {e}")


def resolve_attachment_path(path_str):
    """노드 속성에 저장된 첨부 경로를 실제 파일 경로로 변환."""
    if not path_str:
        return None
    path = Path(path_str)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == ATTACHMENTS_VIRTUAL_ROOT.name:
        relative = Path(*parts[1:]) if len(parts) > 1 else Path()
    else:
        relative = path
    return (attachments_dir / relative).resolve()


atexit.register(lambda: shutil.rmtree(attachments_dir, ignore_errors=True))


def export_to_json(graph, filename='workflow_export.json'):
    """
    그래프를 AI 학습용 JSON 형식으로 내보내기
    """
    workflow_data = {
        "workflow_name": "물류_반송_분석_가이드",
        "description": "전문가 노하우를 구조화한 AI 학습용 워크플로우",
        "steps": []
    }
    
    # 모든 노드 수집
    nodes = graph.all_nodes()
    
    # 노드 ID를 키로 하는 딕셔너리 생성
    node_dict = {}
    step_id_counter = 1  # step_id는 1부터 시작
    for node in nodes:
        # node.id는 속성이지 메서드가 아님 (에러: 'str' object is not callable)
        node_id = node.id  # node.id()가 아니라 node.id (속성)
        
        # node.name도 속성일 수 있음
        node_name = node.name if isinstance(node.name, str) else (node.name() if callable(node.name) else str(node.name))
        
        node_dict[node_id] = {
            'node': node,
            'id': step_id_counter,  # 고유한 step_id 부여
            'type': getattr(node, 'type_', 'unknown'),
            'name': node_name
        }
        step_id_counter += 1  # 다음 step_id 준비
    
    # 각 노드를 순회하며 JSON 구조 생성
    for node_id, node_info in node_dict.items():
        node = node_info['node']
        
        # 노드 위치 정보 가져오기
        pos_x, pos_y = 0, 0
        try:
            # 방법 1: 그래프에서 직접 위치 가져오기
            try:
                graph_pos = graph.get_node_pos(node)
                if graph_pos and len(graph_pos) >= 2:
                    pos_x, pos_y = float(graph_pos[0]), float(graph_pos[1])
                    print(f"  📍 위치 (graph): {node_info['name']} = [{pos_x}, {pos_y}]")
            except:
                pass
            
            # 방법 2: 노드의 pos 속성/메서드
            if pos_x == 0 and pos_y == 0:
                try:
                    if hasattr(node, 'pos'):
                        pos = node.pos
                        if callable(pos):
                            pos = pos()
                        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                            pos_x, pos_y = float(pos[0]), float(pos[1])
                            print(f"  📍 위치 (node.pos): {node_info['name']} = [{pos_x}, {pos_y}]")
                except:
                    pass
            
            # 방법 3: x_pos, y_pos 속성/메서드
            if pos_x == 0 and pos_y == 0:
                try:
                    if hasattr(node, 'x_pos'):
                        if callable(node.x_pos):
                            pos_x = float(node.x_pos())
                            pos_y = float(node.y_pos())
                        else:
                            pos_x = float(node.x_pos)
                            pos_y = float(node.y_pos)
                        print(f"  📍 위치 (x_pos/y_pos): {node_info['name']} = [{pos_x}, {pos_y}]")
                except:
                    pass
                    
        except Exception as e:
            print(f"⚠️ 위치 정보 가져오기 오류 ({node_info['name']}): {e}")
        
        if pos_x == 0 and pos_y == 0:
            print(f"  ⚠️ 위치 정보를 찾을 수 없음: {node_info['name']}")
        
        step = {
            "id": node_info['id'],
            "name": node_info['name'],
            "type": node_info['type'],
            "position": [pos_x, pos_y],  # 위치 정보 저장
            "node_id": node_id,  # 원본 노드 ID 저장 (연결 복원용)
            "connections": []  # 연결 정보 저장
        }
        
        # 파일 첨부 정보 저장
        attached_file = get_attached_file(node) or ''
        if attached_file:
            step['attached_file'] = attached_file
        
        # 노드의 출력 포트에서 연결 정보 수집
        try:
            output_ports = node.output_ports()
            for port_idx, port in enumerate(output_ports):
                connected_ports = port.connected_ports()
                for connected_port in connected_ports:
                    connected_node = connected_port.node()
                    if connected_node:
                        connected_node_id = connected_node.id
                        # 연결된 노드의 ID를 찾기
                        for cid, cinfo in node_dict.items():
                            if cinfo['node'] == connected_node:
                                step['connections'].append({
                                    "from_port": port_idx,
                                    "from_port_name": port.name(),
                                    "to_node_id": cid,
                                    "to_node_step_id": cinfo['id']
                                })
                                break
        except Exception as e:
            print(f"⚠️ 연결 정보 수집 오류 ({node_info['name']}): {e}")
        
        # 노드 타입별로 속성 추출
        if 'TriggerSourceNode' in node_info['type']:
            step['type'] = 'trigger_source'
            step['trigger_source'] = node.get_property('trigger_source') or ''
            step['note'] = node.get_property('note') or ''
            
        elif 'TriggerNode' in node_info['type']:
            step['type'] = 'trigger'
            step['situation'] = node.get_property('situation') or ''
            step['situation_type'] = node.get_property('situation_type') or ''
            step['instruction'] = f"상황: {step['situation']} - 이 상황이 발생했을 때 분석을 시작하세요."
            
        elif 'DataQueryNode' in node_info['type']:
            step['type'] = 'observation'
            step['table'] = node.get_property('target_table') or ''
            step['column'] = node.get_property('target_col') or ''
            step['instruction'] = node.get_property('instruction') or f"{step['table']} 테이블에서 {step['column']} 컬럼을 확인하세요."
            
        elif 'TableNode' in node_info['type']:
            step['type'] = 'table'
            step['target_table'] = node.get_property('target_table') or ''
            step['target_columns'] = node.get_property('target_columns') or ''
            
        elif 'ScreenNode' in node_info['type']:
            step['type'] = 'screen'
            step['screen_name'] = node.get_property('screen_name') or ''
            step['screen_url'] = node.get_property('screen_url') or ''
            step['screen_elements'] = node.get_property('screen_elements') or ''
            
        elif 'SQLNode' in node_info['type']:
            step['type'] = 'sql'
            step['sql_query'] = node.get_property('sql_query') or ''
            step['sql_description'] = node.get_property('sql_description') or ''
            
        elif 'LogNode' in node_info['type']:
            step['type'] = 'log'
            step['log_source'] = node.get_property('log_source') or ''
            step['log_path'] = node.get_property('log_path') or ''
            step['log_pattern'] = node.get_property('log_pattern') or ''
            
        elif 'DecisionNode' in node_info['type']:
            step['type'] = 'reasoning'
            step['condition'] = node.get_property('condition') or ''
            step['reasoning'] = node.get_property('reasoning') or ''
            step['instruction'] = f"조건: {step['condition']} - {step['reasoning']}"
                
        elif 'LoopNode' in node_info['type']:
            step['type'] = 'loop'
            step['target'] = node.get_property('target') or ''
            step['exit_condition'] = node.get_property('exit_condition') or ''
            
        elif 'ConclusionNode' in node_info['type']:
            step['type'] = 'conclusion'
            step['conclusion'] = node.get_property('conclusion') or ''
            step['conclusion_type'] = node.get_property('conclusion_type') or ''
            step['instruction'] = f"결론: {step['conclusion']}"
        
        workflow_data['steps'].append(step)
    
    # ZIP 파일로 저장 (JSON + attachments 폴더) - .flow 확장자 사용
    flow_filename = filename
    if not flow_filename.endswith('.flow'):
        # 확장자를 .flow로 변경
        flow_filename = filename.rsplit('.', 1)[0] + '.flow'
    
    with zipfile.ZipFile(flow_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # JSON 파일을 ZIP에 추가
        json_content = json.dumps(workflow_data, ensure_ascii=False, indent=2)
        zipf.writestr('workflow.json', json_content.encode('utf-8'))
        
        # attachments 폴더의 모든 파일을 ZIP에 추가
        if attachments_dir.exists():
            for file_path in attachments_dir.rglob('*'):
                if file_path.is_file():
                    rel_path = file_path.relative_to(attachments_dir)
                    arcname = ATTACHMENTS_VIRTUAL_ROOT / rel_path
                    zipf.write(file_path, str(arcname).replace('\\', '/'))
                    print(f"  📎 첨부 파일 추가: {arcname}")
    
    print(f"✅ 워크플로우가 '{flow_filename}' 파일로 저장되었습니다!")
    print(f"📊 총 {len(workflow_data['steps'])}개의 단계가 포함되었습니다.")
    print(f"📦 워크플로우 파일에는 JSON과 첨부 파일들이 모두 포함되어 있습니다.")
    
    return workflow_data


def load_from_json(graph, filename):
    """
    ZIP 파일 또는 JSON 파일에서 워크플로우를 불러오기
    ZIP 파일인 경우: workflow.json과 attachments 폴더를 추출
    JSON 파일인 경우: 기존 방식대로 로드 (하위 호환성)
    """
    try:
        clear_attachments_dir()
        # ZIP 파일인지 확인 (.flow 또는 .zip)
        if filename.endswith('.flow') or filename.endswith('.zip'):
            # ZIP 파일에서 불러오기
            with zipfile.ZipFile(filename, 'r') as zipf:
                # workflow.json 추출
                if 'workflow.json' in zipf.namelist():
                    json_content = zipf.read('workflow.json').decode('utf-8')
                    workflow_data = json.loads(json_content)
                else:
                    # 하위 호환성: workflow.json이 없으면 첫 번째 JSON 파일 찾기
                    json_files = [f for f in zipf.namelist() if f.endswith('.json')]
                    if json_files:
                        json_content = zipf.read(json_files[0]).decode('utf-8')
                        workflow_data = json.loads(json_content)
                    else:
                        raise ValueError("ZIP 파일에 JSON 파일이 없습니다.")
                
                # attachments 폴더 추출
                attachments_in_zip = [f for f in zipf.namelist() if f.startswith('attachments/')]
                if attachments_in_zip:
                    for file_info in attachments_in_zip:
                        if file_info.endswith('/'):
                            continue
                        rel_path = Path(file_info)
                        if rel_path.parts and rel_path.parts[0] == ATTACHMENTS_VIRTUAL_ROOT.name:
                            rel_path = Path(*rel_path.parts[1:]) if len(rel_path.parts) > 1 else Path()
                        dest_path = (attachments_dir / rel_path).resolve()
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        with zipf.open(file_info) as source, open(dest_path, 'wb') as target:
                            target.write(source.read())
                        print(f"  📎 첨부 파일 복원: {file_info} -> {dest_path}")
        else:
            # 기존 JSON 파일 방식 (하위 호환성)
            with open(filename, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
        
        print(f"📂 워크플로우 불러오기: {filename}")
        print(f"📊 총 {len(workflow_data.get('steps', []))}개의 단계를 불러옵니다.")
        
        # 기존 노드 모두 삭제
        for node in graph.all_nodes():
            graph.delete_node(node)
        
        # 노드 타입 매핑
        node_type_map = {
            'trigger_source': 'com.samsung.logistics.TriggerSourceNode',
            'trigger': 'com.samsung.logistics.TriggerNode',
            'observation': 'com.samsung.logistics.DataQueryNode',
            'table': 'com.samsung.logistics.TableNode',
            'screen': 'com.samsung.logistics.ScreenNode',
            'log': 'com.samsung.logistics.LogNode',
            'reasoning': 'com.samsung.logistics.DecisionNode',
            'loop': 'com.samsung.logistics.LoopNode',
            'conclusion': 'com.samsung.logistics.ConclusionNode',
        }
        
        # 노드 생성 및 속성 설정
        created_nodes = {}  # step_id -> node 매핑
        node_id_map = {}  # 원본 node_id -> node 매핑 (연결 복원용)
        
        for idx, step in enumerate(workflow_data.get('steps', [])):
            step_type = step.get('type', '')
            node_type = node_type_map.get(step_type)
            
            # 만약 매핑에 없으면 원본 type 문자열에서 직접 추출 시도 (하위 호환성)
            if not node_type:
                # 원본 type이 전체 노드 타입 문자열인 경우 (예: "com.samsung.logistics.TableNode")
                original_type = step.get('type', '')
                if 'com.samsung.logistics.' in original_type:
                    node_type = original_type
                else:
                    print(f"⚠️ 알 수 없는 노드 타입: {step_type}")
                    continue
            
            # 저장된 위치 정보 사용 (없으면 기본 위치)
            if 'position' in step and isinstance(step['position'], list) and len(step['position']) >= 2:
                pos = [float(step['position'][0]), float(step['position'][1])]
            else:
                # 위치 정보가 없으면 가로로 배치
                pos = [100 + idx * 400, 300]  # x는 오른쪽으로, y는 고정 (간격 증가)
            
            # 노드 생성
            node = graph.create_node(node_type, name=step.get('name', f'노드 {idx+1}'), pos=pos)
            
            # 노드 생성 후 attached_file 속성 보장
            ensure_attached_file_property(node)
            
            # 노드 생성 후 위치 재설정 (확실하게)
            if node and 'position' in step:
                try:
                    graph.set_node_pos(node, pos[0], pos[1])
                except:
                    try:
                        if hasattr(node, 'set_pos'):
                            node.set_pos(pos[0], pos[1])
                    except:
                        pass
            
            if node:
                # 노드 타입별 속성 설정
                if step_type == 'trigger_source' or 'TriggerSourceNode' in node_type:
                    if 'trigger_source' in step:
                        node.set_property('trigger_source', step['trigger_source'])
                    if 'note' in step:
                        node.set_property('note', step['note'])
                        
                elif step_type == 'trigger':
                    if 'situation' in step:
                        node.set_property('situation', step['situation'])
                    if 'situation_type' in step:
                        node.set_property('situation_type', step['situation_type'])
                        
                elif step_type == 'observation':
                    if 'table' in step:
                        node.set_property('target_table', step['table'])
                    if 'column' in step:
                        node.set_property('target_col', step['column'])
                    if 'instruction' in step:
                        node.set_property('instruction', step['instruction'])
                        
                elif step_type == 'table' or 'TableNode' in node_type:
                    if 'target_table' in step:
                        node.set_property('target_table', step['target_table'])
                    if 'target_columns' in step:
                        node.set_property('target_columns', step['target_columns'])
                        
                elif step_type == 'screen' or 'ScreenNode' in node_type:
                    if 'screen_name' in step:
                        node.set_property('screen_name', step['screen_name'])
                    if 'screen_url' in step:
                        node.set_property('screen_url', step['screen_url'])
                    if 'screen_elements' in step:
                        node.set_property('screen_elements', step['screen_elements'])
                        
                elif step_type == 'sql' or 'SQLNode' in node_type:
                    if 'sql_query' in step:
                        node.set_property('sql_query', step['sql_query'])
                    if 'sql_description' in step:
                        node.set_property('sql_description', step['sql_description'])
                        
                elif step_type == 'log' or 'LogNode' in node_type:
                    if 'log_source' in step:
                        node.set_property('log_source', step['log_source'])
                    if 'log_path' in step:
                        node.set_property('log_path', step['log_path'])
                    if 'log_pattern' in step:
                        node.set_property('log_pattern', step['log_pattern'])
                        
                elif step_type == 'reasoning':
                    if 'condition' in step:
                        node.set_property('condition', step['condition'])
                    if 'reasoning' in step:
                        node.set_property('reasoning', step['reasoning'])
                        
                elif step_type == 'loop':
                    if 'target' in step:
                        node.set_property('target', step['target'])
                    if 'exit_condition' in step:
                        node.set_property('exit_condition', step['exit_condition'])
                    # 하위 호환성: instruction이 있으면 exit_condition으로 변환
                    elif 'instruction' in step:
                        node.set_property('exit_condition', step['instruction'])
                        
                elif step_type == 'conclusion':
                    if 'conclusion' in step:
                        node.set_property('conclusion', step['conclusion'])
                    if 'conclusion_type' in step:
                        node.set_property('conclusion_type', step['conclusion_type'])
                
                # 파일 첨부 정보 불러오기 (모든 노드 타입에 공통)
                if 'attached_file' in step:
                    set_attached_file(node, step['attached_file'])
                
                step_id = step.get('id')
                created_nodes[step_id] = node
                # 원본 node_id도 저장 (연결 복원용)
                if 'node_id' in step:
                    node_id_map[step['node_id']] = node
                print(f"  ✅ 노드 생성: {step.get('name', 'Unknown')} (step_id={step_id}, node_id={step.get('node_id', 'N/A')}) at {pos}")
            else:
                print(f"  ❌ 노드 생성 실패: {step.get('name', 'Unknown')}")
        
        # 노드 간 연결 복원
        print("\n🔗 노드 연결 복원 중...")
        connection_count = 0
        for step in workflow_data.get('steps', []):
            step_id = step.get('id')
            from_node = created_nodes.get(step_id)
            
            if not from_node:
                print(f"  ⚠️ 노드를 찾을 수 없음 (step_id={step_id}): {step.get('name', 'Unknown')}")
                continue
            
            connections = step.get('connections', [])
            if not connections:
                print(f"  ℹ️ 연결 정보 없음: {step.get('name', 'Unknown')}")
                continue
                
            for conn in connections:
                try:
                    # 연결할 대상 노드 찾기
                    to_step_id = conn.get('to_node_step_id')
                    to_node = created_nodes.get(to_step_id)
                    
                    if not to_node:
                        # node_id로도 시도
                        to_node_id = conn.get('to_node_id')
                        to_node = node_id_map.get(to_node_id)
                        if to_node:
                            print(f"  ℹ️ node_id로 노드 찾음: {to_node_id}")
                    
                    if not to_node:
                        print(f"  ⚠️ 대상 노드를 찾을 수 없음: step_id={to_step_id}, node_id={conn.get('to_node_id', 'N/A')}")
                        continue
                    
                    from_port_idx = conn.get('from_port', 0)
                    from_port_name = conn.get('from_port_name', '')
                    
                    # 출력 포트 찾기
                    output_ports = from_node.output_ports()
                    from_port = None
                    if from_port_idx < len(output_ports):
                        from_port = output_ports[from_port_idx]
                    else:
                        # 포트 이름으로 찾기
                        for port in output_ports:
                            if port.name() == from_port_name:
                                from_port = port
                                break
                    
                    if not from_port:
                        print(f"  ⚠️ 출력 포트를 찾을 수 없음: {from_port_name} (idx={from_port_idx})")
                        continue
                    
                    # 입력 포트 찾기 (첫 번째 입력 포트 사용)
                    input_ports = to_node.input_ports()
                    if not input_ports:
                        print(f"  ⚠️ 입력 포트가 없음: {to_node.name}")
                        continue
                    
                    to_port = input_ports[0]
                    
                    # 연결 시도
                    try:
                        from_port.connect_to(to_port)
                        connection_count += 1
                        to_node_name = to_node.name if hasattr(to_node, 'name') else str(to_node)
                        print(f"  ✅ 연결 성공: {step.get('name')} -> {to_node_name}")
                    except Exception as e1:
                        try:
                            # 대체 연결 방법
                            from_node.set_output(from_port_idx, to_node.input(0))
                            connection_count += 1
                            to_node_name = to_node.name if hasattr(to_node, 'name') else str(to_node)
                            print(f"  ✅ 연결 성공 (대체): {step.get('name')} -> {to_node_name}")
                        except Exception as e2:
                            print(f"  ❌ 연결 실패: {step.get('name')} -> {e1}, {e2}")
                except Exception as e:
                    print(f"  ⚠️ 연결 처리 오류: {e}")
                    import traceback
                    traceback.print_exc()
        
        print(f"✅ 워크플로우 불러오기 완료! ({len(created_nodes)}개 노드, {connection_count}개 연결)")
        return workflow_data
        
    except FileNotFoundError:
        print(f"❌ 파일을 찾을 수 없습니다: {filename}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON 파싱 오류: {e}")
        return None
    except Exception as e:
        print(f"❌ 워크플로우 불러오기 오류: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    # 0. attachments 폴더 생성 (파일 첨부용)
    # 1. 메인 그래프 컨트롤러 생성
    graph = NodeGraph()

    # 연결선 스타일을 '직각(Angled)'으로 변경하여 순서도 느낌 내기
    try:
        # NodeGraphQt 버전에 따라 상수 이름이 다를 수 있음
        try:
            from NodeGraphQt.constants import PIPE_LAYOUT_ANGLE
            graph.set_pipe_style(PIPE_LAYOUT_ANGLE)
        except ImportError:
            # 대체 방법 시도
            try:
                from NodeGraphQt.constants import PIPE_STYLE_ANGLE
                graph.set_pipe_style(PIPE_STYLE_ANGLE)
            except ImportError:
                # 숫자로 직접 시도
                graph.set_pipe_style(1)  # 0=curve, 1=angled
        print("[OK] 연결선 스타일을 직각(Angled)으로 설정")
    except Exception as e:
        print(f"[WARNING] 연결선 스타일 설정 실패: {e}")
    
    # 배경색과 그리드 모드 설정 (순서도 느낌)
    try:
        graph.set_background_color(35, 35, 35)
        graph.set_grid_mode(1)  # 점선 그리드
        print("[OK] 배경색과 그리드 모드 설정 완료")
    except Exception as e:
        print(f"[WARNING] 배경색/그리드 설정 실패: {e}")

    # 2. 모든 커스텀 노드 등록
    graph.register_node(TriggerSourceNode)
    graph.register_node(TriggerNode)
    graph.register_node(DataQueryNode)
    graph.register_node(TableNode)
    graph.register_node(ScreenNode)
    graph.register_node(SQLNode)
    graph.register_node(LogNode)
    graph.register_node(DecisionNode)
    graph.register_node(LoopNode)
    graph.register_node(ConclusionNode)

    # 3. 통합 메인 윈도우 생성
    from PySide2.QtWidgets import QMainWindow, QDockWidget, QWidget, QVBoxLayout, QPushButton
    
    main_window = QMainWindow()
    main_window.setWindowTitle("Samsung Display - AI 학습용 노하우 구조화 도구")
    main_window.resize(1600, 1000)
    
    # 3-1. 중앙에 그래프 뷰어 배치
    viewer = graph.viewer()
    main_window.setCentralWidget(viewer)
    
    # 3-2. 좌측에 노드 추가 패널 (Dock Widget)
    if HAS_NODE_TREE:
        try:
            node_tree = NodeTreeWidget()
            node_tree.set_node_graph(graph)
            
            node_dock = QDockWidget("➕ 노드 추가", main_window)
            node_dock.setWidget(node_tree)
            node_dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
            main_window.addDockWidget(QtCore.Qt.LeftDockWidgetArea, node_dock)
            node_dock.setMinimumWidth(250)
            print("✅ 노드 추가 패널 추가 완료 (좌측)")
        except Exception as e:
            print(f"⚠️ 노드 트리 위젯 추가 실패: {e}")
            HAS_NODE_TREE = False
    
    # 노드 트리가 없으면 버튼 패널로 대체
    if not HAS_NODE_TREE:
        node_panel = QWidget()
        node_layout = QVBoxLayout()
        node_layout.setContentsMargins(10, 5, 10, 10)  # 상단 여백 최소화
        node_layout.setSpacing(10)
        node_panel.setLayout(node_layout)
        
        node_types = [
            ('com.samsung.logistics.TriggerSourceNode', '🌿 트리거', '밝은 초록색'),
            ('com.samsung.logistics.TriggerNode', '🟢 상황 분석', '초록색'),
            ('com.samsung.logistics.DataQueryNode', '🔵 정보 수집', '파란색'),
            ('com.samsung.logistics.TableNode', '📊 테이블', '청록색'),
            ('com.samsung.logistics.ScreenNode', '🖥️ 화면', '보라색'),
            ('com.samsung.logistics.SQLNode', '💾 SQL', '노란색'),
            ('com.samsung.logistics.LogNode', '📝 로그', '주황색'),
            ('com.samsung.logistics.DecisionNode', '🔴 판단', '빨간색'),
            ('com.samsung.logistics.LoopNode', '🟣 반복', '보라색'),
            ('com.samsung.logistics.ConclusionNode', '🟠 결론', '주황색'),
        ]
        
        def add_node_to_graph_from_button(node_type, node_name):
            """버튼 클릭 시 노드 추가"""
            try:
                # 간단하게 기본 위치에 노드 추가 (가로로 배치)
                existing_nodes = graph.all_nodes()
                if existing_nodes:
                    # 기존 노드들의 최대 x 좌표 찾기
                    max_x = 100
                    for n in existing_nodes:
                        try:
                            if hasattr(n, 'pos'):
                                n_pos = n.pos
                                if callable(n_pos):
                                    n_pos = n_pos()
                                if isinstance(n_pos, (list, tuple)) and len(n_pos) >= 2:
                                    max_x = max(max_x, n_pos[0])
                        except:
                            pass
                    # 기존 노드들 오른쪽에 추가 (가로 배치)
                    pos = [max_x + 400, 300]  # x는 오른쪽으로, y는 고정 (간격 증가)
                else:
                    pos = [400, 300]  # 첫 노드는 중앙에
                
                node = graph.create_node(node_type, name=node_name, pos=pos)
                if node:
                    print(f"✅ 노드 추가 완료: {node_name} at {pos}")
                    
                    # 노드 생성 직후 attached_file 속성 보장
                    ensure_attached_file_property(node)
                    
                    # 노드 생성 직후 숫자 속성을 10으로 설정 (속성이 존재하는 경우에만)
                    try:
                        if hasattr(node, 'set_property'):
                            # 여러 가능한 속성 이름 시도
                            for prop_name in ['z_value', 'z', 'layer', 'depth']:
                                try:
                                    # 속성이 존재하는지 먼저 확인
                                    if hasattr(node, '_properties') and prop_name in node._properties:
                                        node.set_property(prop_name, 10)
                                    elif hasattr(node, 'get_property'):
                                        # get_property로 존재 여부 확인 (에러가 나지 않으면 존재)
                                        try:
                                            node.get_property(prop_name)
                                            node.set_property(prop_name, 10)
                                        except:
                                            pass  # 속성이 없으면 건너뜀
                                except:
                                    pass
                    except:
                        pass
                    
                    # 모든 노드의 속성 위젯 가운데 정렬
                    try:
                        # 노드의 그래픽 아이템 찾기
                        if hasattr(node, 'graphics_item'):
                            item = node.graphics_item()
                            if item:
                                # 그래픽 아이템의 위젯 찾기
                                widget = None
                                if hasattr(item, 'widget'):
                                    widget = item.widget()
                                elif hasattr(item, '_widget'):
                                    widget = item._widget
                                
                                if widget:
                                    # 속성 위젯들에 가운데 정렬 스타일 적용 및 클릭 이벤트 처리
                                    # 노드 내부의 모든 위젯을 찾아서 정렬 적용
                                    def apply_center_style(w, node=None):
                                        """위젯과 그 자식 위젯들에 가운데 정렬 스타일 적용 및 클릭 이벤트 처리"""
                                        if isinstance(w, QtWidgets.QComboBox):
                                            w.setStyleSheet("QComboBox { text-align: center; font-size: 9px; }")
                                            # 한 번 클릭으로 드롭다운이 열리도록 이벤트 처리
                                            def on_combo_clicked():
                                                """QComboBox 클릭 시 드롭다운 열기"""
                                                if not w.view().isVisible():
                                                    w.showPopup()
                                            # 마우스 프레스 이벤트 연결
                                            w.mousePressEvent = lambda event: (w.showPopup() if event.button() == QtCore.Qt.LeftButton else QtWidgets.QComboBox.mousePressEvent(w, event))
                                        elif isinstance(w, QtWidgets.QLineEdit):
                                            w.setStyleSheet("QLineEdit { text-align: center; font-size: 9px; }")
                                        elif isinstance(w, QtWidgets.QTextEdit):
                                            w.setStyleSheet("QTextEdit { text-align: center; font-size: 9px; }")
                                        elif isinstance(w, QtWidgets.QLabel):
                                            w.setAlignment(QtCore.Qt.AlignCenter)
                                            # 라벨에도 폰트 크기 설정 (헤더와 동일하게)
                                            font = w.font()
                                            font.setPointSize(9)
                                            w.setFont(font)
                                        
                                        # 자식 위젯들도 재귀적으로 처리
                                        for child in w.findChildren(QtWidgets.QWidget):
                                            apply_center_style(child, node)
                                    
                                    apply_center_style(widget, node)
                    except Exception as e:
                        pass  # 실패해도 계속 진행
                    
                    # 새로 추가된 노드가 화면 중앙에 오도록 캔버스 이동
                    try:
                        view = viewer.view
                        if view:
                            # 방법 1: centerOn 시도
                            try:
                                node_pos = QtCore.QPointF(pos[0], pos[1])
                                view.centerOn(node_pos)
                                print(f"  → 캔버스를 새 노드 위치로 이동 (centerOn): {pos}")
                            except:
                                # 방법 2: 스크롤바 직접 조작
                                try:
                                    # 뷰포트 크기 가져오기
                                    viewport = view.viewport()
                                    if viewport:
                                        viewport_center = viewport.rect().center()
                                        # 노드 위치를 뷰포트 좌표로 변환
                                        scene_pos = view.mapToScene(viewport_center.x(), viewport_center.y())
                                        
                                        # 필요한 스크롤 거리 계산
                                        dx = pos[0] - scene_pos.x()
                                        dy = pos[1] - scene_pos.y()
                                        
                                        # 스크롤바 조작
                                        h_scroll = view.horizontalScrollBar()
                                        v_scroll = view.verticalScrollBar()
                                        
                                        if h_scroll:
                                            current_h = h_scroll.value()
                                            h_scroll.setValue(int(current_h + dx))
                                        
                                        if v_scroll:
                                            current_v = v_scroll.value()
                                            v_scroll.setValue(int(current_v + dy))
                                        
                                        print(f"  → 캔버스를 새 노드 위치로 이동 (스크롤바): {pos}")
                                except Exception as e2:
                                    print(f"  ⚠️ 캔버스 이동 실패: {e2}")
                    except Exception as e:
                        print(f"  ⚠️ 캔버스 이동 실패: {e}")
                    
                    return node
            except Exception as e:
                print(f"❌ 노드 추가 오류 ({node_name}): {e}")
                import traceback
                traceback.print_exc()
            return None
        
        for node_type, node_name, color in node_types:
            btn = QPushButton(node_name)
            btn.setToolTip(f"{node_name} 노드 추가 (클릭하여 추가)")
            btn.setMinimumHeight(40)
            # lambda에서 checked 인자 제거 (QPushButton.clicked는 인자를 전달하지 않음)
            btn.clicked.connect(lambda nt=node_type, nn=node_name: add_node_to_graph_from_button(nt, nn))
            node_layout.addWidget(btn)
        
        # 노드 추가 패널은 나중에 추가 (속성 창 다음에)
        node_dock = None  # 나중에 설정
        
        # 항목 관리 패널 (별도 Dock Widget)
        data_panel = QWidget()
        data_layout = QVBoxLayout()
        data_layout.setContentsMargins(10, 10, 10, 10)
        data_layout.setSpacing(10)
        data_panel.setLayout(data_layout)
        
        data_label = QtWidgets.QLabel("📋 항목 관리")
        data_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        data_layout.addWidget(data_label)
        
        # 탭 위젯으로 목록 관리 UI 구성
        from PySide2.QtWidgets import QTabWidget
        tab_widget = QTabWidget()
        tab_widget.setMaximumHeight(400)
        
        # 탭 1: 테이블 목록 관리
        table_tab = QWidget()
        table_tab_layout = QVBoxLayout()
        table_tab_layout.setContentsMargins(5, 5, 5, 5)
        table_tab.setLayout(table_tab_layout)
        
        # 테이블 목록을 표시할 리스트 위젯
        from PySide2.QtWidgets import QListWidget, QHBoxLayout
        table_list = QListWidget()
        table_list.setMaximumHeight(120)
        table_tab_layout.addWidget(table_list)
        
        # 테이블 추가 입력 필드와 버튼 (여러 줄 입력 가능)
        table_input_layout = QHBoxLayout()
        from PySide2.QtWidgets import QTextEdit
        table_input = QTextEdit()
        table_input.setPlaceholderText("테이블명 입력 (쉼표 또는 줄바꿈으로 구분)")
        table_input.setMaximumHeight(50)
        table_add_btn = QPushButton("➕")
        table_add_btn.setMaximumWidth(40)
        table_add_btn.setMaximumHeight(30)
        table_input_layout.addWidget(table_input)
        table_input_layout.addWidget(table_add_btn)
        table_input_widget = QWidget()
        table_input_widget.setLayout(table_input_layout)
        table_tab_layout.addWidget(table_input_widget)
        
        # 테이블 삭제 버튼
        table_delete_btn = QPushButton("🗑️ 선택 항목 삭제")
        table_delete_btn.setMaximumHeight(30)
        table_tab_layout.addWidget(table_delete_btn)
        
        table_tab_layout.addStretch()
        
        # JSON 파일에서 테이블 목록 로드
        def load_tables():
            """JSON 파일에서 테이블 목록 로드"""
            try:
                with open('tables.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('tables', [])
            except FileNotFoundError:
                # 파일이 없으면 기본 목록 반환
                return ['TB_MCS_LOG', 'TB_WMS_STOCK', 'TB_OHT_STATUS', 'TB_EQP_ALARM', 'TB_TRANSPORT', 'TB_SENSOR']
            except Exception as e:
                print(f"⚠️ 테이블 목록 로드 실패: {e}")
                return []
        
        # JSON 파일에 테이블 목록 저장
        def save_tables(tables_list):
            """JSON 파일에 테이블 목록 저장 (중복 자동 제거)"""
            try:
                # 저장 전에 중복 제거 (이중 안전장치)
                unique_tables = []
                seen = set()
                for table in tables_list:
                    if table and table not in seen:
                        unique_tables.append(table)
                        seen.add(table)
                
                with open('tables.json', 'w', encoding='utf-8') as f:
                    json.dump({'tables': unique_tables}, f, ensure_ascii=False, indent=2)
                print(f"✅ 테이블 목록 저장 완료: {len(unique_tables)}개 (중복 제거됨)")
                # 노드의 드롭다운도 업데이트
                update_node_tables()
            except Exception as e:
                print(f"⚠️ 테이블 목록 저장 실패: {e}")
        
        # 공통 헬퍼 함수: 노드의 콤보박스 위젯 찾기
        def find_combo_widget(node, prop_name):
            """노드의 속성 위젯에서 QComboBox 찾기"""
            widget = None
            # 방법 1: get_widget() 메서드 시도
            if hasattr(node, 'get_widget'):
                try:
                    widget = node.get_widget(prop_name)
                except:
                    pass
            
            # 방법 2: 노드의 내부 속성 딕셔너리에서 찾기
            if not widget and hasattr(node, '_properties'):
                try:
                    prop_dict = node._properties
                    if prop_name in prop_dict:
                        prop_obj = prop_dict[prop_name]
                        if hasattr(prop_obj, 'widget'):
                            widget = prop_obj.widget
                except:
                    pass
            
            # QComboBox 위젯 찾기
            if widget:
                combo = None
                if hasattr(widget, '_combo'):
                    combo = widget._combo
                elif hasattr(widget, 'widget'):
                    combo_widget = widget.widget()
                    if isinstance(combo_widget, QtWidgets.QComboBox):
                        combo = combo_widget
                elif isinstance(widget, QtWidgets.QComboBox):
                    combo = widget
                return combo
            return None
        
        # 노드의 드롭다운 업데이트
        def update_node_tables():
            """모든 TableNode의 드롭다운 업데이트"""
            try:
                tables = load_tables()
                # 모든 노드를 순회하며 TableNode 찾기
                for node in graph.all_nodes():
                    if hasattr(node, '__class__') and node.__class__.__name__ == 'TableNode':
                        try:
                            combo = find_combo_widget(node, 'target_table')
                            if combo:
                                current_value = combo.currentText()
                                combo.clear()
                                combo.addItems(tables)
                                # 기존 값이 목록에 있으면 유지, 없으면 첫 번째 항목으로
                                if current_value in tables:
                                    combo.setCurrentText(current_value)
                                elif tables:
                                    combo.setCurrentText(tables[0])
                                print(f"  ✅ TableNode '{node.name()}'의 드롭다운 업데이트 완료")
                        except Exception as e:
                            print(f"  ⚠️ 노드 '{node.name()}' 업데이트 실패: {e}")
            except Exception as e:
                print(f"⚠️ 노드 테이블 목록 업데이트 실패: {e}")
        
        # 테이블 추가 함수 (여러 개 한 번에 추가 가능)
        def add_table():
            """테이블 목록에 새 테이블 추가 (쉼표 또는 줄바꿈으로 구분, 중복 자동 제거)"""
            input_text = table_input.toPlainText().strip()
            if input_text:
                # 쉼표 또는 줄바꿈으로 구분하여 여러 항목 파싱
                # 먼저 줄바꿈으로 분리, 그 다음 쉼표로 분리
                items = []
                for line in input_text.split('\n'):
                    for item in line.split(','):
                        item = item.strip()
                        if item:
                            items.append(item)
                
                # 현재 리스트에서 모든 항목 가져오기 (중복 포함)
                current_items = []
                for i in range(table_list.count()):
                    current_items.append(table_list.item(i).text())
                
                # 리스트 위젯 자체의 중복 제거 (먼저 정리)
                unique_current = []
                seen = set()
                for item in current_items:
                    if item not in seen:
                        unique_current.append(item)
                        seen.add(item)
                
                # 리스트 위젯을 완전히 재구성 (중복 제거)
                table_list.clear()
                for item in unique_current:
                    table_list.addItem(item)
                
                # 중복 제거된 set 사용
                current_set = set(unique_current)
                
                added_count = 0
                skipped_count = 0
                
                for table_name in items:
                    if table_name not in current_set:
                        table_list.addItem(table_name)
                        current_set.add(table_name)  # 중복 체크를 위해 추가
                        added_count += 1
                    else:
                        skipped_count += 1
                
                # 입력 처리 완료 후 항상 입력 필드 비우기
                table_input.clear()
                
                # 항상 JSON 파일에 저장 (중복 제거된 목록으로)
                all_items = [table_list.item(i).text() for i in range(table_list.count())]
                # 저장할 때도 중복 제거 (이중 안전장치)
                unique_items = []
                seen = set()
                for item in all_items:
                    if item not in seen:
                        unique_items.append(item)
                        seen.add(item)
                
                # 리스트 위젯도 다시 정리 (저장 전 최종 확인)
                if len(unique_items) != len(all_items):
                    table_list.clear()
                    for item in unique_items:
                        table_list.addItem(item)
                
                save_tables(unique_items)
                
                if added_count > 0:
                    print(f"✅ {added_count}개 테이블 추가 완료")
                if skipped_count > 0:
                    print(f"⚠️ {skipped_count}개 테이블은 이미 존재하여 건너뜀")
        
        # 테이블 삭제 함수
        def delete_table():
            """선택된 테이블 삭제"""
            current_item = table_list.currentItem()
            if current_item:
                table_list.takeItem(table_list.row(current_item))
                # JSON 파일에 저장 (중복 제거)
                all_items = [table_list.item(i).text() for i in range(table_list.count())]
                unique_items = []
                seen = set()
                for item in all_items:
                    if item not in seen:
                        unique_items.append(item)
                        seen.add(item)
                # 리스트 위젯도 정리
                if len(unique_items) != len(all_items):
                    table_list.clear()
                    for item in unique_items:
                        table_list.addItem(item)
                save_tables(unique_items)
        
        # 초기 테이블 목록 로드 (중복 제거)
        tables = load_tables()
        # 중복 제거
        seen = set()
        unique_tables = []
        for table in tables:
            if table not in seen:
                unique_tables.append(table)
                seen.add(table)
        # 중복 제거된 목록으로 저장
        if len(unique_tables) != len(tables):
            save_tables(unique_tables)
            print(f"✅ 테이블 목록에서 중복 {len(tables) - len(unique_tables)}개 제거됨")
        for table in unique_tables:
            table_list.addItem(table)
        
        # 탭 2: 상황 유형 목록 관리
        situation_tab = QWidget()
        situation_tab_layout = QVBoxLayout()
        situation_tab_layout.setContentsMargins(5, 5, 5, 5)
        situation_tab.setLayout(situation_tab_layout)
        
        # 상황 유형 목록을 표시할 리스트 위젯
        situation_list = QListWidget()
        situation_list.setMaximumHeight(120)
        situation_tab_layout.addWidget(situation_list)
        
        # 상황 유형 추가 입력 필드와 버튼 (여러 줄 입력 가능)
        situation_input_layout = QHBoxLayout()
        situation_input = QTextEdit()
        situation_input.setPlaceholderText("상황 유형 입력 (쉼표 또는 줄바꿈으로 구분)")
        situation_input.setMaximumHeight(50)
        situation_add_btn = QPushButton("➕")
        situation_add_btn.setMaximumWidth(40)
        situation_add_btn.setMaximumHeight(30)
        situation_input_layout.addWidget(situation_input)
        situation_input_layout.addWidget(situation_add_btn)
        situation_input_widget = QWidget()
        situation_input_widget.setLayout(situation_input_layout)
        situation_tab_layout.addWidget(situation_input_widget)
        
        # 상황 유형 삭제 버튼
        situation_delete_btn = QPushButton("🗑️ 선택 항목 삭제")
        situation_delete_btn.setMaximumHeight(30)
        situation_tab_layout.addWidget(situation_delete_btn)
        
        situation_tab_layout.addStretch()
        
        # 탭 3: 화면 목록 관리
        screen_tab = QWidget()
        screen_tab_layout = QVBoxLayout()
        screen_tab_layout.setContentsMargins(5, 5, 5, 5)
        screen_tab.setLayout(screen_tab_layout)
        
        screen_list = QListWidget()
        screen_list.setMaximumHeight(120)
        screen_tab_layout.addWidget(screen_list)
        
        screen_input_layout = QHBoxLayout()
        screen_input = QTextEdit()
        screen_input.setPlaceholderText("화면명 입력 (쉼표 또는 줄바꿈으로 구분)")
        screen_input.setMaximumHeight(50)
        screen_add_btn = QPushButton("➕")
        screen_add_btn.setMaximumWidth(40)
        screen_add_btn.setMaximumHeight(30)
        screen_input_layout.addWidget(screen_input)
        screen_input_layout.addWidget(screen_add_btn)
        screen_input_widget = QWidget()
        screen_input_widget.setLayout(screen_input_layout)
        screen_tab_layout.addWidget(screen_input_widget)
        
        screen_delete_btn = QPushButton("🗑️ 선택 항목 삭제")
        screen_delete_btn.setMaximumHeight(30)
        screen_tab_layout.addWidget(screen_delete_btn)
        
        screen_tab_layout.addStretch()
        
        # 탭 4: 로그 목록 관리
        log_tab = QWidget()
        log_tab_layout = QVBoxLayout()
        log_tab_layout.setContentsMargins(5, 5, 5, 5)
        log_tab.setLayout(log_tab_layout)
        
        log_list = QListWidget()
        log_list.setMaximumHeight(120)
        log_tab_layout.addWidget(log_list)
        
        log_input_layout = QHBoxLayout()
        log_input = QTextEdit()
        log_input.setPlaceholderText("로그 소스 입력 (쉼표 또는 줄바꿈으로 구분)")
        log_input.setMaximumHeight(50)
        log_add_btn = QPushButton("➕")
        log_add_btn.setMaximumWidth(40)
        log_add_btn.setMaximumHeight(30)
        log_input_layout.addWidget(log_input)
        log_input_layout.addWidget(log_add_btn)
        log_input_widget = QWidget()
        log_input_widget.setLayout(log_input_layout)
        log_tab_layout.addWidget(log_input_widget)
        
        log_delete_btn = QPushButton("🗑️ 선택 항목 삭제")
        log_delete_btn.setMaximumHeight(30)
        log_tab_layout.addWidget(log_delete_btn)
        
        log_tab_layout.addStretch()
        
        # 탭 추가
        tab_widget.addTab(table_tab, "📊 테이블")
        tab_widget.addTab(situation_tab, "📋 상황 유형")
        tab_widget.addTab(screen_tab, "🖥️ 화면")
        tab_widget.addTab(log_tab, "📝 로그")
        
        data_layout.addWidget(tab_widget)
        
        # JSON 파일에서 상황 유형 목록 로드
        def load_situation_types():
            """JSON 파일에서 상황 유형 목록 로드"""
            try:
                with open('situation_types.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('situation_types', [])
            except FileNotFoundError:
                # 파일이 없으면 기본 목록 반환
                return ['반송 지연', '설비 오류', '재고 불일치', '센서 이상', '통신 장애', '기타']
            except Exception as e:
                print(f"⚠️ 상황 유형 목록 로드 실패: {e}")
                return []
        
        # JSON 파일에 상황 유형 목록 저장
        def save_situation_types(types_list):
            """JSON 파일에 상황 유형 목록 저장"""
            try:
                with open('situation_types.json', 'w', encoding='utf-8') as f:
                    json.dump({'situation_types': types_list}, f, ensure_ascii=False, indent=2)
                print(f"✅ 상황 유형 목록 저장 완료: {len(types_list)}개")
                # 노드의 드롭다운도 업데이트
                update_node_situation_types()
            except Exception as e:
                print(f"⚠️ 상황 유형 목록 저장 실패: {e}")
        
        # 노드의 드롭다운 업데이트
        def update_node_situation_types():
            """모든 TriggerNode의 드롭다운 업데이트"""
            try:
                types = load_situation_types()
                # 모든 노드를 순회하며 TriggerNode 찾기
                for node in graph.all_nodes():
                    if hasattr(node, '__class__') and node.__class__.__name__ == 'TriggerNode':
                        try:
                            combo = find_combo_widget(node, 'situation_type')
                            if combo:
                                current_value = combo.currentText()
                                combo.clear()
                                combo.addItems(types)
                                if current_value in types:
                                    combo.setCurrentText(current_value)
                                elif types:
                                    combo.setCurrentText(types[0])
                                print(f"  ✅ TriggerNode '{node.name()}'의 드롭다운 업데이트 완료")
                        except Exception as e:
                            print(f"  ⚠️ 노드 '{node.name()}' 업데이트 실패: {e}")
            except Exception as e:
                print(f"⚠️ 노드 상황 유형 목록 업데이트 실패: {e}")
        
        # 화면 목록 관리 함수들
        def load_screens():
            """JSON 파일에서 화면 목록 로드"""
            try:
                with open('screens.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('screens', [])
            except FileNotFoundError:
                return ['반송 현황 화면', '설비 상태 화면', '재고 관리 화면', '알람 모니터링 화면', '센서 데이터 화면']
            except Exception as e:
                print(f"⚠️ 화면 목록 로드 실패: {e}")
                return []
        
        def save_screens(screens_list):
            """JSON 파일에 화면 목록 저장"""
            try:
                with open('screens.json', 'w', encoding='utf-8') as f:
                    json.dump({'screens': screens_list}, f, ensure_ascii=False, indent=2)
                print(f"✅ 화면 목록 저장 완료: {len(screens_list)}개")
                update_node_screens()
            except Exception as e:
                print(f"⚠️ 화면 목록 저장 실패: {e}")
        
        def update_node_screens():
            """모든 ScreenNode의 드롭다운 업데이트"""
            try:
                screens = load_screens()
                for node in graph.all_nodes():
                    if hasattr(node, '__class__') and node.__class__.__name__ == 'ScreenNode':
                        try:
                            combo = find_combo_widget(node, 'screen_name')
                            if combo:
                                current_value = combo.currentText()
                                combo.clear()
                                combo.addItems(screens)
                                if current_value in screens:
                                    combo.setCurrentText(current_value)
                                elif screens:
                                    combo.setCurrentText(screens[0])
                                print(f"  ✅ ScreenNode '{node.name()}'의 드롭다운 업데이트 완료")
                        except Exception as e:
                            print(f"  ⚠️ 노드 '{node.name()}' 업데이트 실패: {e}")
            except Exception as e:
                print(f"⚠️ 노드 화면 목록 업데이트 실패: {e}")
        
        def add_screen():
            """화면 목록에 새 항목 추가 (중복 자동 제거)"""
            input_text = screen_input.toPlainText().strip()
            if input_text:
                items = []
                for line in input_text.split('\n'):
                    for item in line.split(','):
                        item = item.strip()
                        if item:
                            items.append(item)
                
                # 현재 리스트에서 중복 제거된 목록 가져오기
                current_items = []
                seen = set()
                for i in range(screen_list.count()):
                    item_text = screen_list.item(i).text()
                    if item_text not in seen:
                        current_items.append(item_text)
                        seen.add(item_text)
                
                added_count = 0
                skipped_count = 0
                
                # 중복 제거된 set 사용
                current_set = set(current_items)
                
                for screen_name in items:
                    if screen_name not in current_set:
                        screen_list.addItem(screen_name)
                        current_set.add(screen_name)
                        added_count += 1
                    else:
                        skipped_count += 1
                
                # 입력 처리 완료 후 항상 입력 필드 비우기
                screen_input.clear()
                
                if added_count > 0:
                    # JSON 파일에 저장 (중복 제거된 목록으로)
                    all_items = [screen_list.item(i).text() for i in range(screen_list.count())]
                    # 저장할 때도 중복 제거
                    unique_items = []
                    seen = set()
                    for item in all_items:
                        if item not in seen:
                            unique_items.append(item)
                            seen.add(item)
                    save_screens(unique_items)
                    print(f"✅ {added_count}개 화면 추가 완료")
                if skipped_count > 0:
                    print(f"⚠️ {skipped_count}개 화면은 이미 존재하여 건너뜀")
        
        def delete_screen():
            """선택된 화면 삭제"""
            current_item = screen_list.currentItem()
            if current_item:
                screen_list.takeItem(screen_list.row(current_item))
                save_screens([screen_list.item(i).text() for i in range(screen_list.count())])
        
        # 로그 목록 관리 함수들
        def load_logs():
            """JSON 파일에서 로그 목록 로드"""
            try:
                with open('logs.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('logs', [])
            except FileNotFoundError:
                return ['MCS 로그', '시스템 로그', '애플리케이션 로그', '에러 로그', '접근 로그']
            except Exception as e:
                print(f"⚠️ 로그 목록 로드 실패: {e}")
                return []
        
        def save_logs(logs_list):
            """JSON 파일에 로그 목록 저장"""
            try:
                with open('logs.json', 'w', encoding='utf-8') as f:
                    json.dump({'logs': logs_list}, f, ensure_ascii=False, indent=2)
                print(f"✅ 로그 목록 저장 완료: {len(logs_list)}개")
                update_node_logs()
            except Exception as e:
                print(f"⚠️ 로그 목록 저장 실패: {e}")
        
        def update_node_logs():
            """모든 LogNode의 드롭다운 업데이트"""
            try:
                logs = load_logs()
                for node in graph.all_nodes():
                    if hasattr(node, '__class__') and node.__class__.__name__ == 'LogNode':
                        try:
                            combo = find_combo_widget(node, 'log_source')
                            if combo:
                                current_value = combo.currentText()
                                combo.clear()
                                combo.addItems(logs)
                                if current_value in logs:
                                    combo.setCurrentText(current_value)
                                elif logs:
                                    combo.setCurrentText(logs[0])
                                print(f"  ✅ LogNode '{node.name()}'의 드롭다운 업데이트 완료")
                        except Exception as e:
                            print(f"  ⚠️ 노드 '{node.name()}' 업데이트 실패: {e}")
            except Exception as e:
                print(f"⚠️ 노드 로그 목록 업데이트 실패: {e}")
        
        def add_log():
            """로그 목록에 새 항목 추가 (중복 자동 제거)"""
            input_text = log_input.toPlainText().strip()
            if input_text:
                items = []
                for line in input_text.split('\n'):
                    for item in line.split(','):
                        item = item.strip()
                        if item:
                            items.append(item)
                
                # 현재 리스트에서 중복 제거된 목록 가져오기
                current_items = []
                seen = set()
                for i in range(log_list.count()):
                    item_text = log_list.item(i).text()
                    if item_text not in seen:
                        current_items.append(item_text)
                        seen.add(item_text)
                
                added_count = 0
                skipped_count = 0
                
                # 중복 제거된 set 사용
                current_set = set(current_items)
                
                for log_name in items:
                    if log_name not in current_set:
                        log_list.addItem(log_name)
                        current_set.add(log_name)
                        added_count += 1
                    else:
                        skipped_count += 1
                
                # 입력 처리 완료 후 항상 입력 필드 비우기
                log_input.clear()
                
                if added_count > 0:
                    # JSON 파일에 저장 (중복 제거된 목록으로)
                    all_items = [log_list.item(i).text() for i in range(log_list.count())]
                    # 저장할 때도 중복 제거
                    unique_items = []
                    seen = set()
                    for item in all_items:
                        if item not in seen:
                            unique_items.append(item)
                            seen.add(item)
                    save_logs(unique_items)
                    print(f"✅ {added_count}개 로그 추가 완료")
                if skipped_count > 0:
                    print(f"⚠️ {skipped_count}개 로그는 이미 존재하여 건너뜀")
        
        def delete_log():
            """선택된 로그 삭제"""
            current_item = log_list.currentItem()
            if current_item:
                log_list.takeItem(log_list.row(current_item))
                save_logs([log_list.item(i).text() for i in range(log_list.count())])
        
        # 상황 유형 추가 함수 (여러 개 한 번에 추가 가능)
        def add_situation_type():
            """상황 유형 목록에 새 항목 추가 (쉼표 또는 줄바꿈으로 구분, 중복 자동 제거)"""
            input_text = situation_input.toPlainText().strip()
            if input_text:
                # 쉼표 또는 줄바꿈으로 구분하여 여러 항목 파싱
                # 먼저 줄바꿈으로 분리, 그 다음 쉼표로 분리
                items = []
                for line in input_text.split('\n'):
                    for item in line.split(','):
                        item = item.strip()
                        if item:
                            items.append(item)
                
                # 현재 리스트에서 중복 제거된 목록 가져오기
                current_items = []
                seen = set()
                for i in range(situation_list.count()):
                    item_text = situation_list.item(i).text()
                    if item_text not in seen:
                        current_items.append(item_text)
                        seen.add(item_text)
                
                added_count = 0
                skipped_count = 0
                
                # 중복 제거된 set 사용
                current_set = set(current_items)
                
                for type_name in items:
                    if type_name not in current_set:
                        situation_list.addItem(type_name)
                        current_set.add(type_name)  # 중복 체크를 위해 추가
                        added_count += 1
                    else:
                        skipped_count += 1
                
                # 입력 처리 완료 후 항상 입력 필드 비우기
                situation_input.clear()
                
                if added_count > 0:
                    # JSON 파일에 저장 (중복 제거된 목록으로)
                    all_items = [situation_list.item(i).text() for i in range(situation_list.count())]
                    # 저장할 때도 중복 제거
                    unique_items = []
                    seen = set()
                    for item in all_items:
                        if item not in seen:
                            unique_items.append(item)
                            seen.add(item)
                    save_situation_types(unique_items)
                    print(f"✅ {added_count}개 상황 유형 추가 완료")
                if skipped_count > 0:
                    print(f"⚠️ {skipped_count}개 상황 유형은 이미 존재하여 건너뜀")
        
        # 상황 유형 삭제 함수
        def delete_situation_type():
            """선택된 상황 유형 삭제"""
            current_item = situation_list.currentItem()
            if current_item:
                situation_list.takeItem(situation_list.row(current_item))
                # JSON 파일에 저장
                save_situation_types([situation_list.item(i).text() for i in range(situation_list.count())])
        
        # 초기 목록 로드 (중복 제거)
        tables = load_tables()
        # 중복 제거
        seen = set()
        unique_tables = []
        for table in tables:
            if table not in seen:
                unique_tables.append(table)
                seen.add(table)
        # 중복 제거된 목록으로 저장
        if len(unique_tables) != len(tables):
            save_tables(unique_tables)
            print(f"✅ 테이블 목록에서 중복 {len(tables) - len(unique_tables)}개 제거됨")
        for table in unique_tables:
            table_list.addItem(table)
        
        situation_types = load_situation_types()
        # 중복 제거
        seen = set()
        unique_situation_types = []
        for stype in situation_types:
            if stype not in seen:
                unique_situation_types.append(stype)
                seen.add(stype)
        # 중복 제거된 목록으로 저장
        if len(unique_situation_types) != len(situation_types):
            save_situation_types(unique_situation_types)
            print(f"✅ 상황 유형 목록에서 중복 {len(situation_types) - len(unique_situation_types)}개 제거됨")
        for stype in unique_situation_types:
            situation_list.addItem(stype)
        
        screens = load_screens()
        # 중복 제거
        seen = set()
        unique_screens = []
        for screen in screens:
            if screen not in seen:
                unique_screens.append(screen)
                seen.add(screen)
        # 중복 제거된 목록으로 저장
        if len(unique_screens) != len(screens):
            save_screens(unique_screens)
            print(f"✅ 화면 목록에서 중복 {len(screens) - len(unique_screens)}개 제거됨")
        for screen in unique_screens:
            screen_list.addItem(screen)
        
        logs = load_logs()
        # 중복 제거
        seen = set()
        unique_logs = []
        for log in logs:
            if log not in seen:
                unique_logs.append(log)
                seen.add(log)
        # 중복 제거된 목록으로 저장
        if len(unique_logs) != len(logs):
            save_logs(unique_logs)
            print(f"✅ 로그 목록에서 중복 {len(logs) - len(unique_logs)}개 제거됨")
        for log in unique_logs:
            log_list.addItem(log)
        
        # 이벤트 연결
        table_add_btn.clicked.connect(add_table)
        table_delete_btn.clicked.connect(delete_table)
        
        situation_add_btn.clicked.connect(add_situation_type)
        situation_delete_btn.clicked.connect(delete_situation_type)
        
        screen_add_btn.clicked.connect(add_screen)
        screen_delete_btn.clicked.connect(delete_screen)
        
        log_add_btn.clicked.connect(add_log)
        log_delete_btn.clicked.connect(delete_log)
        
        # 하단에 스페이서 추가 (관리 UI가 위로 올라가도록)
        data_layout.addStretch()
        
        # 항목 관리 패널은 나중에 추가 (노드 추가 창 다음에)
        data_dock = None  # 나중에 설정
    
    # 첨부 파일 열기 헬퍼 함수
    def open_attached_file(node):
        """노드에 첨부된 파일을 OS 기본 프로그램으로 열기"""
        try:
            attached_file = get_attached_file(node) or ''
            if not attached_file:
                return False
            file_path = resolve_attachment_path(attached_file)
            if not file_path:
                return False
            
            if file_path.exists():
                # OS 기본 프로그램으로 파일 열기
                if sys.platform == 'win32':
                    os.startfile(str(file_path))
                elif sys.platform == 'darwin':
                    os.system(f'open "{file_path}"')
                else:
                    os.system(f'xdg-open "{file_path}"')
                print(f"✅ 파일 열기: {file_path}")
                return True
            else:
                QtWidgets.QMessageBox.warning(
                    None, 
                    '파일 없음', 
                    f'첨부된 파일을 찾을 수 없습니다.\n{file_path}'
                )
                return False
        except Exception as e:
            print(f"⚠️ 파일 열기 실패: {e}")
            QtWidgets.QMessageBox.critical(None, '오류', f'파일을 열 수 없습니다.\n{e}')
            return False
    
    
    # 3-3. 파일 첨부 패널 (별도 Dock Widget)
    file_attachment_panel = QWidget()
    file_attachment_layout = QVBoxLayout()
    file_attachment_layout.setContentsMargins(10, 10, 10, 10)
    file_attachment_layout.setSpacing(10)
    file_attachment_panel.setLayout(file_attachment_layout)
    
    # 제목
    file_label = QtWidgets.QLabel("📎 파일 첨부")
    file_label.setStyleSheet("font-weight: bold; font-size: 16px; padding: 12px;")
    file_attachment_layout.addWidget(file_label)
    
    # 선택된 노드 표시
    selected_node_label = QtWidgets.QLabel("선택된 노드: 없음")
    selected_node_label.setStyleSheet("font-size: 13px; color: #888; padding: 6px;")
    file_attachment_layout.addWidget(selected_node_label)
    
    # 파일 선택 버튼
    file_select_btn = QPushButton("📁 파일 선택")
    file_select_btn.setMinimumHeight(40)
    file_select_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
    file_attachment_layout.addWidget(file_select_btn)
    
    # 첨부 파일 정보 라벨
    attached_file_label = QtWidgets.QLabel("첨부된 파일: (없음)")
    attached_file_label.setStyleSheet("font-size: 13px; padding: 6px;")
    attached_file_label.setWordWrap(True)
    file_attachment_layout.addWidget(attached_file_label)
    
    # 파일 열기 버튼
    open_file_btn = QPushButton("📂 파일 열기")
    open_file_btn.setMinimumHeight(36)
    open_file_btn.setStyleSheet("font-size: 13px;")
    open_file_btn.setEnabled(False)
    file_attachment_layout.addWidget(open_file_btn)
    
    # 파일 삭제 버튼
    file_delete_btn = QPushButton("🗑️ 파일 삭제")
    file_delete_btn.setMinimumHeight(36)
    file_delete_btn.setStyleSheet("font-size: 13px;")
    file_delete_btn.setEnabled(False)  # 파일이 없으면 비활성화
    file_attachment_layout.addWidget(file_delete_btn)
    
    file_attachment_layout.addStretch()
    
    # 파일 첨부 패널 업데이트 함수
    def update_file_attachment_panel():
        """선택된 노드에 따라 파일 첨부 패널 업데이트 (모든 노드 지원)"""
        selected = graph.selected_nodes()
        if selected and len(selected) > 0:
            node = selected[0]
            node_name = node.name if isinstance(node.name, str) else (node.name() if callable(node.name) else str(node.name))
            selected_node_label.setText(f"선택된 노드: {node_name}")
            
            # 첨부 파일 확인
            try:
                attached_file = get_attached_file(node) or ''
                if attached_file:
                    file_path = Path(attached_file)
                    file_name = file_path.name if file_path.name else attached_file
                    attached_file_label.setText(f"첨부된 파일: {file_name}")
                    attached_file_label.setToolTip(attached_file)  # 전체 경로를 툴팁으로 표시
                    open_file_btn.setEnabled(True)
                    file_delete_btn.setEnabled(True)
                else:
                    attached_file_label.setText("첨부된 파일: (없음)")
                    attached_file_label.setToolTip('')
                    open_file_btn.setEnabled(False)
                    file_delete_btn.setEnabled(False)
            except:
                attached_file_label.setText("첨부된 파일: (없음)")
                attached_file_label.setToolTip('')
                open_file_btn.setEnabled(False)
                file_delete_btn.setEnabled(False)
        else:
            selected_node_label.setText("선택된 노드: 없음")
            attached_file_label.setText("첨부된 파일: (노드를 선택하세요)")
            attached_file_label.setToolTip('')
            open_file_btn.setEnabled(False)
            file_delete_btn.setEnabled(False)
    
    # 파일 선택 버튼 클릭 이벤트
    def on_file_select_clicked():
        selected = graph.selected_nodes()
        if not selected:
            QtWidgets.QMessageBox.warning(None, '알림', '노드를 먼저 선택하세요.')
            return
        
        node = selected[0]
        ensure_attached_file_property(node)
        
        # 파일 선택 다이얼로그
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None,
            '파일 선택',
            '',
            '모든 파일 (*.*);;이미지 (*.png *.jpg *.jpeg *.gif *.bmp);;문서 (*.pdf *.doc *.docx *.txt);;기타 (*.*)'
        )
        
        if file_path:
            try:
                # 파일을 attachments 폴더로 복사
                source_path = Path(file_path)
                file_name = source_path.name
                # 파일명에 노드 ID 추가하여 고유하게 만들기
                node_id = node.id if hasattr(node, 'id') else str(id(node))
                file_stem = source_path.stem
                file_suffix = source_path.suffix
                unique_name = f"{file_stem}_{node_id[:8]}{file_suffix}"
                dest_path = attachments_dir / unique_name
                
                # 파일 복사
                shutil.copy2(source_path, dest_path)
                
                # 노드 속성에 상대 경로 저장 (attached_file 사용)
                relative_path = (ATTACHMENTS_VIRTUAL_ROOT / unique_name).as_posix()
                set_attached_file(node, relative_path)
                
                # 패널 업데이트 (즉시 및 약간의 지연 후)
                update_file_attachment_panel()
                QtCore.QTimer.singleShot(100, update_file_attachment_panel)
                
                QtWidgets.QMessageBox.information(
                    None, 
                    '성공', 
                    f"파일이 첨부되었습니다.\n{file_name}\n\n'📂 파일 열기' 버튼으로 열 수 있습니다."
                )
                print(f"✅ 파일 첨부 완료: {relative_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(None, '오류', f'파일 첨부 실패: {str(e)}')
                print(f"❌ 파일 첨부 실패: {e}")
    
    # 파일 열기 버튼 클릭 이벤트
    def on_open_file_clicked():
        selected = graph.selected_nodes()
        if not selected:
            QtWidgets.QMessageBox.warning(None, '알림', '노드를 먼저 선택하세요.')
            return
        
        node = selected[0]
        if not open_attached_file(node):
            QtWidgets.QMessageBox.information(None, '알림', '첨부된 파일이 없습니다.')
    
    # 파일 삭제 버튼 클릭 이벤트
    def on_file_delete_clicked():
        selected = graph.selected_nodes()
        if not selected:
            return
        
        node = selected[0]
        
        try:
            attached_file = get_attached_file(node) or ''
            if attached_file:
                real_path = resolve_attachment_path(attached_file)
                if not real_path:
                    return
                reply = QtWidgets.QMessageBox.question(
                    None,
                    '파일 삭제',
                    '첨부된 파일을 삭제하시겠습니까?',
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No
                )
                
                if reply == QtWidgets.QMessageBox.Yes:
                    # 파일 삭제
                    if real_path.exists():
                        real_path.unlink()
                        print(f"✅ 파일 삭제: {real_path}")
                    
                    # 노드 속성에서 제거
                    set_attached_file(node, '')
                    
                    # 패널 업데이트
                    update_file_attachment_panel()
                    
                    QtWidgets.QMessageBox.information(None, '완료', '파일이 삭제되었습니다.')
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, '오류', f'파일 삭제 실패: {str(e)}')
            print(f"❌ 파일 삭제 실패: {e}")
    
    # 이벤트 연결
    file_select_btn.clicked.connect(on_file_select_clicked)
    open_file_btn.clicked.connect(on_open_file_clicked)
    file_delete_btn.clicked.connect(on_file_delete_clicked)
    
    # 파일 첨부 Dock Widget 생성 (좌측 최상단)
    file_attachment_dock = QDockWidget("📎 파일 첨부", main_window)
    file_attachment_dock.setWidget(file_attachment_panel)
    file_attachment_dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
    main_window.addDockWidget(QtCore.Qt.LeftDockWidgetArea, file_attachment_dock)
    file_attachment_dock.setMinimumWidth(350)
    file_attachment_dock.setMinimumHeight(300)
    print("✅ 파일 첨부 패널 추가 완료 (좌측 상단)")

    # 파일 첨부 패널 아래에 노드/데이터 패널 정렬
    dock_anchor = file_attachment_dock

    if HAS_NODE_TREE:
        try:
            if node_dock:
                main_window.splitDockWidget(dock_anchor, node_dock, QtCore.Qt.Vertical)
                dock_anchor = node_dock
        except Exception as e:
            print(f"⚠️ 노드 트리 Dock 재배치 실패: {e}")
    else:
        node_dock = QDockWidget("➕ 노드 추가", main_window)
        node_dock.setWidget(node_panel)
        node_dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        main_window.addDockWidget(QtCore.Qt.LeftDockWidgetArea, node_dock)
        main_window.splitDockWidget(dock_anchor, node_dock, QtCore.Qt.Vertical)
        node_dock.setMinimumWidth(200)
        dock_anchor = node_dock
        print("✅ 노드 추가 버튼 패널 추가 완료 (좌측 중간)")

    data_dock = QDockWidget("📋 항목 관리", main_window)
    data_dock.setWidget(data_panel)
    data_dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
    main_window.addDockWidget(QtCore.Qt.LeftDockWidgetArea, data_dock)
    main_window.splitDockWidget(dock_anchor, data_dock, QtCore.Qt.Vertical)
    data_dock.setMinimumWidth(300)
    data_dock.setMinimumHeight(400)
    print("✅ 항목 관리 패널 추가 완료 (좌측 하단)")
    
    # 노드 선택/해제 시 파일 첨부 패널 업데이트
    try:
        if hasattr(graph, 'nodes_selected'):
            def on_nodes_selected_for_file():
                # 선택된 노드가 없을 때도 처리
                QtCore.QTimer.singleShot(50, update_file_attachment_panel)
            graph.nodes_selected.connect(on_nodes_selected_for_file)
        
        # 노드 선택 해제 이벤트 연결
        if hasattr(graph, 'nodes_deselected'):
            def on_nodes_deselected_for_file():
                QtCore.QTimer.singleShot(50, update_file_attachment_panel)
            graph.nodes_deselected.connect(on_nodes_deselected_for_file)
    except:
        pass
    
    # QGraphicsScene의 selectionChanged 시그널 사용 (가장 확실한 방법)
    try:
        viewer = graph.viewer()
        if viewer:
            view = None
            if hasattr(viewer, 'view'):
                view = viewer.view
            elif hasattr(viewer, 'get_view'):
                view = viewer.get_view()
            elif isinstance(viewer, QtWidgets.QGraphicsView):
                view = viewer
            
            if view and view.scene():
                scene = view.scene()
                # selectionChanged 시그널 연결
                scene.selectionChanged.connect(lambda: QtCore.QTimer.singleShot(50, update_file_attachment_panel))
                print("✅ Scene selectionChanged 이벤트 연결 완료")
    except Exception as e:
        print(f"⚠️ Scene selectionChanged 이벤트 연결 실패: {e}")
    
    # 주기적으로 선택 상태 확인 (백업 방법)
    selection_check_timer = QtCore.QTimer()
    selection_check_timer.timeout.connect(update_file_attachment_panel)
    selection_check_timer.start(200)  # 200ms마다 확인
    print("✅ 선택 상태 주기적 확인 타이머 시작")
    
    # 캔버스 클릭 시 선택 해제 감지 (추가 보완)
    try:
        viewer = graph.viewer()
        if viewer:
            view = None
            if hasattr(viewer, 'view'):
                view = viewer.view
            elif hasattr(viewer, 'get_view'):
                view = viewer.get_view()
            elif isinstance(viewer, QtWidgets.QGraphicsView):
                view = viewer
            
            if view:
                original_mouse_press = view.mousePressEvent
                
                def custom_mouse_press(event):
                    """커스텀 마우스 클릭 이벤트 핸들러"""
                    # 원래 이벤트 처리
                    original_mouse_press(event)
                    
                    # 약간의 지연 후 패널 업데이트 (선택 상태가 변경된 후)
                    QtCore.QTimer.singleShot(100, update_file_attachment_panel)
                
                view.mousePressEvent = custom_mouse_press
                print("✅ 캔버스 클릭 이벤트 연결 완료")
    except Exception as e:
        print(f"⚠️ 캔버스 클릭 이벤트 연결 실패: {e}")
    
    # 초기 상태 설정
    update_file_attachment_panel()
    
    # 3-4. 메인 윈도우 표시
    main_window.show()
    
    # 3-5. 노드 복사/붙여넣기 기능
    copied_nodes_data = []  # 복사된 노드 데이터 저장
    last_mouse_pos = [0, 0]  # 마지막 마우스 위치 저장 (붙여넣기용)
    
    # Fit to View 기능 - 모든 노드가 보이도록 줌
    def fit_to_view():
        """모든 노드가 보이도록 적절한 배율로 줌하고 노드들의 중심으로 이동"""
        try:
            nodes = graph.all_nodes()
            if not nodes:
                print("⚠️ 표시할 노드가 없습니다.")
                return
            
            # viewer의 view 가져오기 (여러 방법 시도)
            view = None
            
            # 방법 1: viewer.view 속성
            try:
                if hasattr(viewer, 'view'):
                    view = viewer.view
            except:
                pass
            
            # 방법 2: viewer의 자식 위젯 중 QGraphicsView 찾기
            if not view:
                try:
                    if hasattr(viewer, 'findChildren'):
                        children = viewer.findChildren(QtWidgets.QGraphicsView)
                        if children:
                            view = children[0]
                except:
                    pass
            
            # 방법 3: viewer 자체가 QGraphicsView인 경우
            if not view:
                try:
                    if isinstance(viewer, QtWidgets.QGraphicsView):
                        view = viewer
                except:
                    pass
            
            # 방법 4: graph.viewer()를 통해 다시 가져오기
            if not view:
                try:
                    temp_viewer = graph.viewer()
                    if hasattr(temp_viewer, 'view'):
                        view = temp_viewer.view
                    elif isinstance(temp_viewer, QtWidgets.QGraphicsView):
                        view = temp_viewer
                    elif hasattr(temp_viewer, 'findChildren'):
                        children = temp_viewer.findChildren(QtWidgets.QGraphicsView)
                        if children:
                            view = children[0]
                except Exception as e:
                    print(f"  ⚠️ graph.viewer() 시도 실패: {e}")
            
            # 방법 5: viewer.scene()을 통해 접근
            if not view:
                try:
                    if hasattr(viewer, 'scene'):
                        scene = viewer.scene()
                        if scene and hasattr(scene, 'views'):
                            views = scene.views()
                            if views:
                                view = views[0]
                except Exception as e:
                    print(f"  ⚠️ viewer.scene() 접근 실패: {e}")
            
            # 방법 6: graph.scene()을 통해 접근
            if not view:
                try:
                    if hasattr(graph, 'scene'):
                        scene = graph.scene()
                        if scene and hasattr(scene, 'views'):
                            views = scene.views()
                            if views:
                                view = views[0]
                except Exception as e:
                    print(f"  ⚠️ graph.scene() 접근 실패: {e}")
            
            if not view:
                print(f"⚠️ 뷰를 찾을 수 없습니다. (viewer 타입: {type(viewer)})")
                # 디버깅 정보 출력
                try:
                    print(f"  viewer 속성: {dir(viewer)}")
                    if hasattr(viewer, 'view'):
                        print(f"  viewer.view: {viewer.view}")
                except:
                    pass
                return
            
            # 모든 노드의 위치 수집
            min_x, min_y = float('inf'), float('inf')
            max_x, max_y = float('-inf'), float('-inf')
            
            for node in nodes:
                try:
                    # 노드 위치 가져오기 (여러 방법 시도)
                    x, y = None, None
                    node_name = node.name() if callable(node.name) else (node.name if hasattr(node, 'name') else str(node))
                    
                    # 방법 1: graph.get_node_pos() 시도
                    try:
                        if hasattr(graph, 'get_node_pos'):
                            pos = graph.get_node_pos(node)
                            if pos and len(pos) >= 2:
                                x, y = float(pos[0]), float(pos[1])
                                print(f"  📍 노드 '{node_name}' 위치 (graph.get_node_pos): [{x}, {y}]")
                    except Exception as e1:
                        print(f"  ⚠️ graph.get_node_pos 실패 ({node_name}): {e1}")
                    
                    # 방법 2: node.pos 속성/메서드
                    if x is None or y is None:
                        try:
                            if hasattr(node, 'pos'):
                                n_pos = node.pos
                                if callable(n_pos):
                                    n_pos = n_pos()
                                if isinstance(n_pos, (list, tuple)) and len(n_pos) >= 2:
                                    x, y = float(n_pos[0]), float(n_pos[1])
                                    print(f"  📍 노드 '{node_name}' 위치 (node.pos): [{x}, {y}]")
                        except Exception as e2:
                            print(f"  ⚠️ node.pos 실패 ({node_name}): {e2}")
                    
                    # 방법 3: x_pos, y_pos 속성/메서드
                    if x is None or y is None:
                        try:
                            if hasattr(node, 'x_pos'):
                                if callable(node.x_pos):
                                    x = float(node.x_pos())
                                    y = float(node.y_pos())
                                else:
                                    x = float(node.x_pos)
                                    y = float(node.y_pos)
                                print(f"  📍 노드 '{node_name}' 위치 (x_pos/y_pos): [{x}, {y}]")
                        except Exception as e3:
                            print(f"  ⚠️ x_pos/y_pos 실패 ({node_name}): {e3}")
                    
                    # 방법 4: node.viewer() 또는 node.graph()를 통한 접근
                    if x is None or y is None:
                        try:
                            # NodeGraphQt의 경우 노드가 viewer를 통해 접근 가능할 수 있음
                            if hasattr(node, 'viewer'):
                                viewer = node.viewer()
                                if viewer and hasattr(viewer, 'get_node_pos'):
                                    pos = viewer.get_node_pos(node)
                                    if pos and len(pos) >= 2:
                                        x, y = float(pos[0]), float(pos[1])
                                        print(f"  📍 노드 '{node_name}' 위치 (node.viewer): [{x}, {y}]")
                        except Exception as e4:
                            print(f"  ⚠️ node.viewer 실패 ({node_name}): {e4}")
                    
                    # 방법 5: 노드의 그래픽 아이템 직접 접근
                    if x is None or y is None:
                        try:
                            if hasattr(node, 'graphics_item'):
                                item = node.graphics_item()
                                if item:
                                    pos = item.pos()
                                    if pos:
                                        x, y = float(pos.x()), float(pos.y())
                                        print(f"  📍 노드 '{node_name}' 위치 (graphics_item.pos): [{x}, {y}]")
                        except Exception as e5:
                            print(f"  ⚠️ graphics_item 실패 ({node_name}): {e5}")
                    
                    if x is None or y is None:
                        print(f"  ❌ 노드 '{node_name}' 위치를 찾을 수 없습니다. (사용 가능한 속성: {[attr for attr in dir(node) if not attr.startswith('_')][:10]})")
                        continue
                    
                    # 노드 크기 추정 (대략적인 크기)
                    node_width = 200  # 대략적인 노드 너비
                    node_height = 150  # 대략적인 노드 높이
                    
                    min_x = min(min_x, x - node_width / 2)
                    min_y = min(min_y, y - node_height / 2)
                    max_x = max(max_x, x + node_width / 2)
                    max_y = max(max_y, y + node_height / 2)
                except Exception as e:
                    print(f"  ⚠️ 노드 위치 가져오기 실패: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            if min_x == float('inf'):
                print("⚠️ 노드 위치를 찾을 수 없습니다.")
                return
            
            # 경계에 여백 추가
            padding = 100
            min_x -= padding
            min_y -= padding
            max_x += padding
            max_y += padding
            
            # 노드 영역의 크기
            nodes_width = max_x - min_x
            nodes_height = max_y - min_y
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            
            # 뷰포트 크기 가져오기
            viewport = view.viewport()
            if not viewport:
                print("⚠️ 뷰포트를 찾을 수 없습니다.")
                return
            
            viewport_rect = viewport.rect()
            viewport_width = viewport_rect.width()
            viewport_height = viewport_rect.height()
            
            if viewport_width <= 0 or viewport_height <= 0:
                print("⚠️ 뷰포트 크기가 유효하지 않습니다.")
                return
            
            # 적절한 줌 레벨 계산
            scale_x = viewport_width / nodes_width if nodes_width > 0 else 1.0
            scale_y = viewport_height / nodes_height if nodes_height > 0 else 1.0
            # 더 작은 배율을 사용하여 모든 노드가 보이도록
            target_scale = min(scale_x, scale_y) * 0.9  # 90%로 약간 여유 공간
            
            # 최소/최대 줌 레벨 제한
            target_scale = max(0.1, min(5.0, target_scale))
            
            # 현재 줌 레벨
            current_scale = view.transform().m11()
            scale_factor = target_scale / current_scale
            
            # 줌 수행
            view.scale(scale_factor, scale_factor)
            
            # 노드들의 중심으로 이동
            # centerOn이 제대로 작동하지 않을 수 있으므로 여러 방법 시도
            try:
                # 방법 1: centerOn 시도 (가장 간단)
                center_point = QtCore.QPointF(center_x, center_y)
                view.centerOn(center_point)
                
                # 방법 2: ensureVisible로 노드 영역이 보이도록 보장
                # (이미 centerOn으로 중심을 맞췄지만, 혹시 모를 경우를 대비)
                scene_rect = QtCore.QRectF(min_x, min_y, nodes_width, nodes_height)
                view.ensureVisible(scene_rect, 50, 50)  # 50px 여백
                
                # 방법 3: 스크롤바 직접 조정 (더 정확한 제어)
                # centerOn 후에도 정확히 맞지 않을 수 있으므로 미세 조정
                viewport = view.viewport()
                if viewport:
                    viewport_rect = viewport.rect()
                    viewport_center = viewport_rect.center()
                    
                    # 현재 뷰포트 중심이 가리키는 씬 좌표
                    current_center_scene = view.mapToScene(viewport_center)
                    
                    # 차이가 있으면 미세 조정
                    dx = center_x - current_center_scene.x()
                    dy = center_y - current_center_scene.y()
                    
                    if abs(dx) > 1 or abs(dy) > 1:  # 1픽셀 이상 차이가 있으면 조정
                        h_scroll = view.horizontalScrollBar()
                        v_scroll = view.verticalScrollBar()
                        
                        if h_scroll:
                            # 씬 좌표 차이를 뷰 좌표로 변환
                            scene_point1 = QtCore.QPointF(0, 0)
                            scene_point2 = QtCore.QPointF(dx, 0)
                            view_point1 = view.mapFromScene(scene_point1)
                            view_point2 = view.mapFromScene(scene_point2)
                            pixel_dx = view_point2.x() - view_point1.x()
                            h_scroll.setValue(h_scroll.value() + int(pixel_dx))
                        
                        if v_scroll:
                            scene_point1 = QtCore.QPointF(0, 0)
                            scene_point2 = QtCore.QPointF(0, dy)
                            view_point1 = view.mapFromScene(scene_point1)
                            view_point2 = view.mapFromScene(scene_point2)
                            pixel_dy = view_point2.y() - view_point1.y()
                            v_scroll.setValue(v_scroll.value() + int(pixel_dy))
                        
                        print(f"  → 미세 조정: ({dx:.1f}, {dy:.1f})")
                
                print(f"  → 중심 이동 완료: ({center_x:.1f}, {center_y:.1f})")
            except Exception as e:
                print(f"  ⚠️ 중심 이동 실패: {e}")
                import traceback
                traceback.print_exc()
            
            print(f"✅ Fit to View 완료: {len(nodes)}개 노드, 줌 레벨 {target_scale:.2f}, 중심 ({center_x:.1f}, {center_y:.1f})")
        except Exception as e:
            print(f"❌ Fit to View 실패: {e}")
            import traceback
            traceback.print_exc()
    
    def on_copy_nodes():
        """선택된 노드들을 복사 (연결 정보 포함)"""
        try:
            selected_nodes = [n for n in graph.all_nodes() if n.selected()]
            if not selected_nodes:
                print("⚠️ 복사할 노드가 선택되지 않았습니다.")
                return
            
            # 선택된 노드 ID 집합 (빠른 검색용)
            selected_node_ids = {node.id for node in selected_nodes}
            
            # 노드 데이터 수집
            copied_nodes_data.clear()
            node_id_map = {}  # 원본 노드 ID -> 인덱스 매핑
            
            for idx, node in enumerate(selected_nodes):
                node_id = node.id
                node_id_map[node_id] = idx
                
                node_data = {
                    'id': node_id,  # 원본 노드 ID 저장
                    'type': node.type_,
                    'name': node.name if isinstance(node.name, str) else (node.name() if callable(node.name) else str(node.name)),
                    'properties': {},
                    'pos': None,
                    'connections': []  # 연결 정보 저장
                }
                
                # 위치 정보 가져오기
                try:
                    pos = graph.get_node_pos(node)
                    if pos and len(pos) >= 2:
                        node_data['pos'] = [float(pos[0]), float(pos[1])]
                except:
                    try:
                        if hasattr(node, 'pos'):
                            pos = node.pos
                            if callable(pos):
                                pos = pos()
                            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                                node_data['pos'] = [float(pos[0]), float(pos[1])]
                    except:
                        pass
                
                # 연결 정보 수집 (선택된 노드들 간의 연결만)
                try:
                    output_ports = node.output_ports()
                    for port_idx, port in enumerate(output_ports):
                        connected_ports = port.connected_ports()
                        for connected_port in connected_ports:
                            connected_node = connected_port.node()
                            if connected_node and connected_node.id in selected_node_ids:
                                # 선택된 노드들 간의 연결만 저장
                                input_ports = connected_node.input_ports()
                                to_port_idx = None
                                for i, inp_port in enumerate(input_ports):
                                    if inp_port == connected_port:
                                        to_port_idx = i
                                        break
                                
                                if to_port_idx is not None:
                                    node_data['connections'].append({
                                        'from_port': port_idx,
                                        'to_node_id': connected_node.id,
                                        'to_port': to_port_idx
                                    })
                except Exception as e:
                    print(f"  ⚠️ 연결 정보 수집 실패 ({node_data['name']}): {e}")
                
                # 모든 속성 저장
                try:
                    if hasattr(node, '_properties'):
                        for prop_name, prop_value in node._properties.items():
                            if hasattr(prop_value, 'value'):
                                node_data['properties'][prop_name] = prop_value.value
                            elif hasattr(prop_value, 'get_value'):
                                node_data['properties'][prop_name] = prop_value.get_value()
                            else:
                                node_data['properties'][prop_name] = prop_value
                except:
                    pass
                
                # get_property로도 시도
                common_props = ['situation', 'situation_type', 'trigger_source', 'note', 
                               'target_table', 'target_columns', 'screen_name', 'screen_url', 
                               'screen_elements', 'log_source', 'log_path', 'log_pattern',
                               'condition', 'reasoning', 'target', 'instruction', 
                               'conclusion', 'conclusion_type', 'description']
                for prop_name in common_props:
                    try:
                        prop_value = node.get_property(prop_name)
                        if prop_value is not None:
                            node_data['properties'][prop_name] = prop_value
                    except:
                        pass
                
                copied_nodes_data.append(node_data)
            
            print(f"✅ {len(copied_nodes_data)}개 노드 복사 완료 (연결 {sum(len(n.get('connections', [])) for n in copied_nodes_data)}개 포함)")
        except Exception as e:
            print(f"❌ 노드 복사 실패: {e}")
            import traceback
            traceback.print_exc()
    
    def on_paste_nodes():
        """복사된 노드들을 붙여넣기 (연결 정보 복원)"""
        try:
            if not copied_nodes_data:
                print("⚠️ 붙여넣을 노드가 없습니다.")
                return
            
            # 붙여넣기 위치 (마우스 위치 또는 마지막 클릭 위치)
            paste_x, paste_y = last_mouse_pos[0], last_mouse_pos[1]  # 기본값은 마지막 클릭 위치
            
            # 마우스 위치 가져오기 시도
            try:
                # viewer 객체에서 view 가져오기 (여러 방법 시도)
                view = None
                try:
                    if hasattr(viewer, 'view'):
                        view = viewer.view
                except:
                    pass
                
                if not view:
                    try:
                        if hasattr(viewer, 'widget'):
                            view = viewer.widget()
                    except:
                        pass
                
                if not view:
                    try:
                        # viewer의 자식 위젯 중 QGraphicsView 찾기
                        for child in viewer.findChildren(QtWidgets.QGraphicsView):
                            view = child
                            break
                    except:
                        pass
                
                if view:
                    # 방법 1: viewport를 통한 정확한 마우스 위치 가져오기 (줌 레벨 고려)
                    try:
                        viewport = view.viewport()
                        if viewport:
                            # 전역 마우스 위치
                            global_pos = QtGui.QCursor.pos()
                            # 뷰포트 내부 상대 위치 (정확한 변환)
                            local_pos = viewport.mapFromGlobal(global_pos)
                            # QPointF로 변환하여 정확도 향상
                            local_pos_f = QtCore.QPointF(local_pos)
                            # 씬 좌표로 변환 (줌 레벨 자동 고려)
                            scene_pos = view.mapToScene(local_pos_f)
                            paste_x = float(scene_pos.x())
                            paste_y = float(scene_pos.y())
                            # 마지막 마우스 위치 업데이트
                            last_mouse_pos[0] = paste_x
                            last_mouse_pos[1] = paste_y
                            print(f"  📍 붙여넣기 위치: 마우스 위치 ({paste_x:.1f}, {paste_y:.1f})")
                    except Exception as e1:
                        # 방법 2: view를 통한 직접 변환 (줌 레벨 고려)
                        try:
                            global_pos = QtGui.QCursor.pos()
                            # view의 전역 위치 가져오기
                            view_global = view.mapToGlobal(QtCore.QPoint(0, 0))
                            # view 내부 상대 위치
                            local_pos = QtCore.QPoint(global_pos.x() - view_global.x(), 
                                                     global_pos.y() - view_global.y())
                            # QPointF로 변환하여 정확도 향상
                            local_pos_f = QtCore.QPointF(local_pos)
                            # 씬 좌표로 변환 (줌 레벨 자동 고려)
                            scene_pos = view.mapToScene(local_pos_f)
                            paste_x = float(scene_pos.x())
                            paste_y = float(scene_pos.y())
                            # 마지막 마우스 위치 업데이트
                            last_mouse_pos[0] = paste_x
                            last_mouse_pos[1] = paste_y
                            print(f"  📍 붙여넣기 위치: 마우스 위치 ({paste_x:.1f}, {paste_y:.1f})")
                        except Exception as e2:
                            raise Exception(f"방법1: {e1}, 방법2: {e2}")
                else:
                    # view를 찾을 수 없으면 viewer를 직접 사용
                    try:
                        global_pos = QtGui.QCursor.pos()
                        # viewer가 QWidget인 경우 직접 사용
                        if hasattr(viewer, 'mapFromGlobal'):
                            local_pos = viewer.mapFromGlobal(global_pos)
                            paste_x = local_pos.x()
                            paste_y = local_pos.y()
                            print(f"  📍 붙여넣기 위치: 마우스 위치 ({paste_x:.1f}, {paste_y:.1f})")
                        else:
                            raise Exception("viewer에 mapFromGlobal 메서드가 없습니다")
                    except Exception as e3:
                        raise Exception(f"viewer 직접 사용 실패: {e3}")
            except Exception as e:
                print(f"  ⚠️ 마우스 위치 가져오기 실패, 기본 위치 사용: {e}")
                # 기본 위치 사용
                paste_x, paste_y = 50, 50
            
            # 첫 번째 노드의 원본 위치 계산 (상대 위치 유지용)
            first_node_pos = None
            if copied_nodes_data and copied_nodes_data[0].get('pos'):
                first_node_pos = copied_nodes_data[0]['pos']
            
            # 원본 노드 ID -> 새 노드 매핑
            node_id_mapping = {}  # 원본 ID -> 새 노드
            
            pasted_nodes = []
            for idx, node_data in enumerate(copied_nodes_data):
                try:
                    # 노드 생성 위치 계산
                    if node_data.get('pos') and first_node_pos:
                        # 상대 위치 유지
                        rel_x = node_data['pos'][0] - first_node_pos[0]
                        rel_y = node_data['pos'][1] - first_node_pos[1]
                        pos = [paste_x + rel_x, paste_y + rel_y]
                    else:
                        # 위치 정보가 없으면 순차적으로 배치
                        pos = [paste_x + idx * 30, paste_y + idx * 30]
                    
                    node = graph.create_node(node_data['type'], name=node_data['name'], pos=pos)
                    if node:
                        # 속성 복원
                        for prop_name, prop_value in node_data.get('properties', {}).items():
                            try:
                                node.set_property(prop_name, prop_value)
                            except:
                                pass
                        
                        # 원본 노드 ID와 새 노드 매핑 저장
                        original_id = node_data.get('id')
                        if original_id:
                            node_id_mapping[original_id] = node
                        
                        pasted_nodes.append(node)
                except Exception as e:
                    print(f"⚠️ 노드 붙여넣기 실패 ({node_data.get('name', 'Unknown')}): {e}")
            
            # 연결 복원
            connection_count = 0
            for node_data in copied_nodes_data:
                original_id = node_data.get('id')
                from_node = node_id_mapping.get(original_id)
                
                if not from_node:
                    continue
                
                # 연결 정보 복원
                for conn in node_data.get('connections', []):
                    try:
                        to_original_id = conn.get('to_node_id')
                        to_node = node_id_mapping.get(to_original_id)
                        
                        if not to_node:
                            continue
                        
                        from_port_idx = conn.get('from_port', 0)
                        to_port_idx = conn.get('to_port', 0)
                        
                        # 출력 포트와 입력 포트 찾기
                        try:
                            output_ports = from_node.output_ports()
                            input_ports = to_node.input_ports()
                            
                            if from_port_idx < len(output_ports) and to_port_idx < len(input_ports):
                                from_port = output_ports[from_port_idx]
                                to_port = input_ports[to_port_idx]
                                
                                # 연결 시도
                                try:
                                    from_port.connect_to(to_port)
                                    connection_count += 1
                                except:
                                    # 대체 방법 시도
                                    try:
                                        if hasattr(from_node, 'set_output'):
                                            from_node.set_output(from_port_idx, to_node.input(to_port_idx))
                                            connection_count += 1
                                    except:
                                        pass
                        except Exception as e:
                            print(f"  ⚠️ 연결 복원 실패: {e}")
                    except Exception as e:
                        print(f"  ⚠️ 연결 처리 오류: {e}")
            
            if pasted_nodes:
                # 붙여넣은 노드들을 선택 상태로
                for node in pasted_nodes:
                    try:
                        node.set_selected(True)
                    except:
                        pass
                print(f"✅ {len(pasted_nodes)}개 노드 붙여넣기 완료 (연결 {connection_count}개 복원)")
        except Exception as e:
            print(f"❌ 노드 붙여넣기 실패: {e}")
            import traceback
            traceback.print_exc()
    
    # 3-5. 우클릭 메뉴에 노드 추가 옵션 추가
    # 마우스 위치를 저장할 변수
    last_context_menu_pos = [0, 0]
    
    def add_node_to_graph(node_type, node_name):
        """그래프에 노드를 추가하는 함수"""
        try:
            # 저장된 마우스 위치 사용
            pos = last_context_menu_pos.copy()
            
            node = graph.create_node(node_type, name=node_name, pos=pos)
            if node:
                print(f"✅ 노드 추가 완료: {node_name} at {pos}")
                
                # 새로 추가된 노드가 화면 중앙에 오도록 캔버스 이동
                try:
                    view = viewer.view
                    if view:
                        # 방법 1: centerOn 시도
                        try:
                            node_pos = QtCore.QPointF(pos[0], pos[1])
                            view.centerOn(node_pos)
                            print(f"  → 캔버스를 새 노드 위치로 이동 (centerOn): {pos}")
                        except:
                            # 방법 2: 스크롤바 직접 조작
                            try:
                                # 뷰포트 크기 가져오기
                                viewport = view.viewport()
                                if viewport:
                                    viewport_center = viewport.rect().center()
                                    # 노드 위치를 뷰포트 좌표로 변환
                                    scene_pos = view.mapToScene(viewport_center.x(), viewport_center.y())
                                    
                                    # 필요한 스크롤 거리 계산
                                    dx = pos[0] - scene_pos.x()
                                    dy = pos[1] - scene_pos.y()
                                    
                                    # 스크롤바 조작
                                    h_scroll = view.horizontalScrollBar()
                                    v_scroll = view.verticalScrollBar()
                                    
                                    if h_scroll:
                                        current_h = h_scroll.value()
                                        h_scroll.setValue(int(current_h + dx))
                                    
                                    if v_scroll:
                                        current_v = v_scroll.value()
                                        v_scroll.setValue(int(current_v + dy))
                                    
                                    print(f"  → 캔버스를 새 노드 위치로 이동 (스크롤바): {pos}")
                            except Exception as e2:
                                print(f"  ⚠️ 캔버스 이동 실패: {e2}")
                except Exception as e:
                    print(f"  ⚠️ 캔버스 이동 실패: {e}")
                
                return node
            else:
                print(f"❌ 노드 추가 실패: {node_name}")
                return None
        except Exception as e:
            print(f"❌ 노드 추가 오류 ({node_name}): {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # 그래프 뷰어의 context menu에 노드 추가 메뉴 추가
    try:
        # 그래프 뷰어의 scene에서 context menu 가져오기
        scene = viewer.scene()
        if scene:
            # 커스텀 context menu 생성
            from PySide2.QtWidgets import QMenu, QAction
            
            def create_node_menu(event):
                """우클릭 시 노드 추가 메뉴 생성"""
                menu = QMenu(viewer)
                
                # 노드 추가 서브메뉴
                add_node_menu = menu.addMenu("➕ 노드 추가 (Add Node)")
                
                # 각 노드 타입별 액션 추가
                node_types = [
                    ('com.samsung.logistics.TriggerSourceNode', '상황 트리거 (Trigger Source)', '🌿'),
                    ('com.samsung.logistics.TriggerNode', '상황 (Trigger)', '🟢'),
                    ('com.samsung.logistics.DataQueryNode', '정보 수집 (Data Gathering)', '🔵'),
                    ('com.samsung.logistics.DecisionNode', '판단 (Decision)', '🔴'),
                    ('com.samsung.logistics.LoopNode', '반복 (Loop)', '🟣'),
                    ('com.samsung.logistics.ConclusionNode', '결론 (Conclusion)', '🟠'),
                ]
                
                for node_type, node_name, icon in node_types:
                    action = add_node_menu.addAction(f"{icon} {node_name}")
                    action.triggered.connect(lambda checked, nt=node_type, nn=node_name: add_node_to_graph(nt, nn))
                
                menu.addSeparator()
                
                # 기존 메뉴 항목들도 추가 (Undo, Redo 등)
                undo_action = menu.addAction("↶ Undo (Ctrl+Z)")
                undo_action.triggered.connect(lambda: graph.undo())
                
                redo_action = menu.addAction("↷ Redo (Ctrl+Y)")
                redo_action.triggered.connect(lambda: graph.redo())
                
                menu.addSeparator()
                
                # 복사
                copy_action = menu.addAction("📋 복사 (Ctrl+C)")
                copy_action.triggered.connect(lambda: on_copy_nodes())
                
                # 붙여넣기
                paste_action = menu.addAction("📄 붙여넣기 (Ctrl+V)")
                paste_action.triggered.connect(lambda: on_paste_nodes())
                
                menu.addSeparator()
                
                # 전체 선택
                select_all_action = menu.addAction("전체 선택 (Ctrl+A)")
                select_all_action.triggered.connect(lambda: [n.set_selected(True) for n in graph.all_nodes()])
                
                # 선택 해제
                deselect_action = menu.addAction("선택 해제")
                deselect_action.triggered.connect(lambda: [n.set_selected(False) for n in graph.all_nodes()])
                
                menu.addSeparator()
                
                # Fit to View
                fit_action = menu.addAction("🔍 전체 보기 (Fit to View)")
                fit_action.triggered.connect(fit_to_view)
                
                return menu
            
            # 그래프 뷰어에 context menu 이벤트 연결
            view = viewer.view
            if view:
                def on_context_menu(pos):
                    """우클릭 시 호출되는 함수"""
                    # 마우스 위치를 그래프 좌표로 변환
                    scene_pos = view.mapToScene(pos)
                    # last_context_menu_pos를 직접 수정 (외부 변수이므로 nonlocal 불필요)
                    last_context_menu_pos[0] = scene_pos.x()
                    last_context_menu_pos[1] = scene_pos.y()
                    # 마지막 마우스 위치도 업데이트 (붙여넣기용)
                    last_mouse_pos[0] = scene_pos.x()
                    last_mouse_pos[1] = scene_pos.y()
                    # 메뉴 표시
                    menu = create_node_menu(pos)
                    menu.exec_(view.mapToGlobal(pos))
                
                view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                view.customContextMenuRequested.connect(on_context_menu)
                print("✅ 우클릭 메뉴 추가 완료")
            else:
                print("⚠️ 뷰어의 view를 찾을 수 없습니다")
        else:
            print("⚠️ 뷰어의 scene을 찾을 수 없습니다")
    except Exception as e:
        import traceback
        print(f"⚠️ 우클릭 메뉴 추가 실패: {e}")
        traceback.print_exc()

    # 3-6. 마우스로 캔버스 이동 기능 추가 (스페이스바 + 드래그)
    try:
        from PySide2.QtCore import Qt, QPoint
        from PySide2.QtGui import QMouseEvent
        
        # 뷰어의 view에 접근
        view = viewer.view
        if not view:
            print("⚠️ 뷰어의 view를 찾을 수 없습니다")
        else:
            print(f"✅ View 객체 찾음: {type(view)}")
            
            # 스페이스바 + 드래그로 캔버스 이동
            space_pressed = False
            last_pan_point = None
            
            original_mousePressEvent = view.mousePressEvent
            original_mouseMoveEvent = view.mouseMoveEvent
            original_mouseReleaseEvent = view.mouseReleaseEvent
            original_keyPressEvent = view.keyPressEvent
            original_keyReleaseEvent = view.keyReleaseEvent
            original_wheelEvent = view.wheelEvent
            
            def custom_keyPressEvent(event):
                """스페이스바 감지"""
                global space_pressed
                if event.key() == Qt.Key_Space:
                    space_pressed = True
                    view.setCursor(QtCore.Qt.ClosedHandCursor)
                    event.accept()
                    return
                original_keyPressEvent(event)
            
            def custom_keyReleaseEvent(event):
                """스페이스바 릴리즈"""
                global space_pressed, last_pan_point
                if event.key() == Qt.Key_Space:
                    space_pressed = False
                    last_pan_point = None
                    view.setCursor(QtCore.Qt.ArrowCursor)
                    event.accept()
                    return
                original_keyReleaseEvent(event)
            
            def custom_mousePressEvent(event):
                """마우스 클릭 시 스페이스바가 눌려있으면 패닝 시작"""
                global last_pan_point
                if space_pressed:
                    # 스페이스바가 눌려있으면 어떤 버튼이든 패닝 시작
                    last_pan_point = event.pos()
                    event.accept()
                    return
                original_mousePressEvent(event)
            
            def custom_mouseMoveEvent(event):
                """마우스 이동 시 스페이스바가 눌려있으면 캔버스 이동"""
                global last_pan_point
                if space_pressed:
                    # 스페이스바가 눌려있으면 마우스 이동만으로도 패닝 시작
                    if last_pan_point is None:
                        # 처음 이동 시작
                        last_pan_point = event.pos()
                        return
                    
                    # 마우스 이동 거리 계산
                    delta = event.pos() - last_pan_point
                    
                    # 스크롤바를 직접 조작하여 캔버스 이동
                    h_scroll = view.horizontalScrollBar()
                    v_scroll = view.verticalScrollBar()
                    
                    if h_scroll:
                        current_h = h_scroll.value()
                        h_scroll.setValue(current_h - delta.x())
                    
                    if v_scroll:
                        current_v = v_scroll.value()
                        v_scroll.setValue(current_v - delta.y())
                    
                    last_pan_point = event.pos()
                    event.accept()
                    return
                original_mouseMoveEvent(event)
            
            def custom_mouseReleaseEvent(event):
                """마우스 릴리즈 시 패닝 종료"""
                global last_pan_point
                if event.button() == Qt.LeftButton:
                    last_pan_point = None
                original_mouseReleaseEvent(event)
            
            def custom_wheelEvent(event):
                """마우스 휠 이벤트 - 마우스 커서 위치를 중심으로 줌"""
                try:
                    # 마우스 커서 위치를 씬 좌표로 변환 (줌 전)
                    mouse_pos = event.pos()
                    scene_pos_before = view.mapToScene(mouse_pos)
                    
                    # 줌 배율 계산 (휠 델타에 따라)
                    delta = event.angleDelta().y()
                    zoom_factor = 1.15 if delta > 0 else 1.0 / 1.15
                    
                    # 현재 줌 레벨 가져오기
                    current_scale = view.transform().m11()
                    new_scale = current_scale * zoom_factor
                    
                    # 최소/최대 줌 레벨 제한
                    min_scale = 0.1
                    max_scale = 5.0
                    new_scale = max(min_scale, min(max_scale, new_scale))
                    
                    if new_scale == current_scale:
                        # 줌 레벨이 변경되지 않으면 기본 동작
                        original_wheelEvent(event)
                        return
                    
                    # 줌 수행
                    scale_factor = new_scale / current_scale
                    view.scale(scale_factor, scale_factor)
                    
                    # 줌 후 마우스 커서가 가리키는 씬 좌표 계산
                    scene_pos_after = view.mapToScene(mouse_pos)
                    
                    # 줌 전후의 차이 계산
                    delta_x = scene_pos_before.x() - scene_pos_after.x()
                    delta_y = scene_pos_before.y() - scene_pos_after.y()
                    
                    # 스크롤바를 조정하여 마우스 커서 위치가 동일한 씬 좌표를 가리키도록
                    h_scroll = view.horizontalScrollBar()
                    v_scroll = view.verticalScrollBar()
                    
                    if h_scroll:
                        current_h = h_scroll.value()
                        # 줌 레벨에 따라 스크롤 조정
                        h_scroll.setValue(int(current_h + delta_x * new_scale))
                    
                    if v_scroll:
                        current_v = v_scroll.value()
                        v_scroll.setValue(int(current_v + delta_y * new_scale))
                    
                    event.accept()
                except Exception as e:
                    # 오류 발생 시 기본 동작 수행
                    print(f"  ⚠️ 줌 처리 오류: {e}")
                    try:
                        original_wheelEvent(event)
                    except:
                        pass
            
            # 이벤트 핸들러 연결
            view.keyPressEvent = custom_keyPressEvent
            view.keyReleaseEvent = custom_keyReleaseEvent
            view.mousePressEvent = custom_mousePressEvent
            view.mouseMoveEvent = custom_mouseMoveEvent
            view.mouseReleaseEvent = custom_mouseReleaseEvent
            view.wheelEvent = custom_wheelEvent
            
            print("✅ 마우스 캔버스 이동 기능 추가 완료")
            print("   💡 스페이스바를 누른 채로 마우스를 드래그하면 캔버스를 이동할 수 있습니다.")
    except Exception as e:
        import traceback
        print(f"⚠️ 마우스 캔버스 이동 기능 추가 실패: {e}")
        traceback.print_exc()

    # 4. 예시 워크플로우 생성 (반송 지연 분석 시나리오) - 주석 처리 (빈 캔버스로 시작)
    # print("\n🔧 예시 워크플로우 생성 시작...")
    # 예시 워크플로우를 생성하지 않고 빈 캔버스로 시작
    print("\n✅ 빈 캔버스로 시작합니다. 노드를 추가하거나 JSON 파일을 열어주세요.")
    """
    try:
    try:
        print("  - Trigger 노드 생성 중...")
        trigger = graph.create_node(
            'com.samsung.logistics.TriggerNode',
            name='상황: 반송 지연',
            pos=[0, 0]
        )
        print(f"    결과: {trigger}")
        if trigger:
            trigger.set_property('situation', '반송 명령 후 10분 지연')
            trigger.set_property('situation_type', '반송 지연')
            print("    ✅ Trigger 노드 생성 및 속성 설정 완료")
        else:
            print("    ❌ Trigger 노드 생성 실패")
        
        loop = graph.create_node(
            'com.samsung.logistics.LoopNode',
            name='반복: 모든 OHT 차량',
            pos=[250, 0]
        )
        if loop:
            loop.set_property('target', '해당 라인의 모든 OHT 차량')
            loop.set_property('instruction', '해당 라인의 모든 OHT 차량에 대해 검사')
        
        query1 = graph.create_node(
            'com.samsung.logistics.DataQueryNode',
            name='OHT 상태 조회',
            pos=[500, 0]
        )
        if query1:
            query1.set_property('target_table', 'TB_OHT_STATUS')
            query1.set_property('target_col', 'Battery_Level')
            query1.set_property('instruction', 'OHT 상태 로그에서 배터리 잔량을 확인해')
        
        decision1 = graph.create_node(
            'com.samsung.logistics.DecisionNode',
            name='배터리 체크',
            pos=[750, 0]
        )
        if decision1:
            decision1.set_property('condition', 'battery_level < 20')
            decision1.set_property('reasoning', '배터리가 20% 이하면 충전 대기 상태일 수 있음')
        
        conclusion1 = graph.create_node(
            'com.samsung.logistics.ConclusionNode',
            name='결론: 충전 대기',
            pos=[1000, -100]
        )
        if conclusion1:
            conclusion1.set_property('conclusion', '충전 대기로 인한 지연')
            conclusion1.set_property('conclusion_type', '원인 파악')
        
        query2 = graph.create_node(
            'com.samsung.logistics.DataQueryNode',
            name='센서 감지 이력',
            pos=[1000, 100]
        )
        if query2:
            query2.set_property('target_table', 'TB_SENSOR')
            query2.set_property('target_col', 'Location')
            query2.set_property('instruction', '구간 센서 감지 이력을 확인해')
        
        # 노드 연결
        if trigger and loop:
            try:
                trigger.get_output(0).connect_to(loop.get_input(0))
            except:
                try:
                    trigger.set_output(0, loop.input(0))
                except:
                    pass
        
        if loop and query1:
            try:
                loop.get_output(0).connect_to(query1.get_input(0))
            except:
                try:
                    loop.set_output(0, query1.input(0))
                except:
                    pass
        
        if query1 and decision1:
            try:
                query1.get_output(0).connect_to(decision1.get_input(0))
            except:
                try:
                    query1.set_output(0, decision1.input(0))
                except:
                    pass
        
        if decision1 and conclusion1:
            try:
                decision1.get_output(0).connect_to(conclusion1.get_input(0))
            except:
                try:
                    decision1.set_output(0, conclusion1.input(0))
                except:
                    pass
        
        if decision1 and query2:
            try:
                decision1.get_output(1).connect_to(query2.get_input(0))
            except:
                try:
                    decision1.set_output(1, query2.input(0))
                except:
                    pass
        print("\n✅ 예시 워크플로우 생성 완료!")
                    
    except Exception as e:
        import traceback
        print(f"\n❌ 예시 워크플로우 생성 중 오류 발생:")
        print(f"   에러: {e}")
        print(f"   상세:")
        traceback.print_exc()
        print("\n노드를 수동으로 추가할 수 있습니다.")
    """

    # 5. 새로 만들기 기능
    def on_new_workflow():
        """새 워크플로우 시작 (모든 노드 삭제)"""
        reply = QtWidgets.QMessageBox.question(
            main_window,
            "새로 만들기",
            "현재 워크플로우를 삭제하고 새로 시작하시겠습니까?\n(저장하지 않은 변경사항은 손실됩니다.)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # 모든 노드 삭제
            nodes = graph.all_nodes()
            for node in nodes:
                graph.delete_node(node)
            clear_attachments_dir()
            update_file_attachment_panel()
            print("✅ 새 워크플로우를 시작합니다.")
            QtWidgets.QMessageBox.information(
                main_window,
                "새로 만들기",
                "새 워크플로우를 시작합니다."
            )
    
    # 6. JSON Import/Export 기능 추가
    def on_open_json():
        """워크플로우 파일 열기"""
        try:
            filename, _ = QtWidgets.QFileDialog.getOpenFileName(
                main_window,
                "워크플로우 파일 열기",
                "",
                "워크플로우 파일 (*.flow);;ZIP 파일 (*.zip);;JSON 파일 (*.json);;모든 파일 (*.*)"
            )
            if filename:
                print(f"\n📂 워크플로우 파일 열기 시작: {filename}")
                try:
                    result = load_from_json(graph, filename)
                    if result:
                        file_type = "워크플로우 파일" if filename.endswith('.flow') else ("ZIP 파일" if filename.endswith('.zip') else "JSON 파일")
                        update_file_attachment_panel()
                        QtWidgets.QMessageBox.information(
                            main_window,
                            "불러오기 완료 ✅",
                            f"워크플로우가 성공적으로 불러와졌습니다!\n\n파일: {filename}\n형식: {file_type}\n노드 수: {len(result.get('steps', []))}개\n\n(워크플로우 파일에서 첨부 파일들도 함께 복원되었습니다.)"
                        )
                        print(f"✅ 불러오기 완료: {len(result.get('steps', []))}개의 노드가 불러와졌습니다.")
                    else:
                        QtWidgets.QMessageBox.warning(
                            main_window,
                            "불러오기 실패",
                            "워크플로우를 불러올 수 없습니다."
                        )
                except Exception as e:
                    import traceback
                    error_msg = f"불러오기 중 오류가 발생했습니다:\n\n{str(e)}"
                    print(f"❌ 불러오기 오류: {error_msg}")
                    QtWidgets.QMessageBox.critical(
                        main_window,
                        "불러오기 오류 ❌",
                        error_msg
                    )
        except Exception as e:
            print(f"❌ 파일 다이얼로그 오류: {e}")
            QtWidgets.QMessageBox.critical(
                main_window,
                "오류",
                f"파일 열기 대화상자를 열 수 없습니다:\n{str(e)}"
            )
    
    def on_export_json():
        try:
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                viewer,
                "워크플로우 저장",
                "workflow_export.flow",
                "워크플로우 파일 (*.flow);;ZIP 파일 (*.zip);;JSON 파일 (*.json);;모든 파일 (*.*)"
            )
            if filename:
                # 워크플로우 파일로 저장 (기본값)
                if not filename.endswith('.flow') and not filename.endswith('.zip') and not filename.endswith('.json'):
                    filename += '.flow'
                print(f"\n💾 워크플로우 저장 시작: {filename}")
                try:
                    result = export_to_json(graph, filename)
                    file_type = "워크플로우 파일" if filename.endswith('.flow') else ("ZIP 파일" if filename.endswith('.zip') else "JSON 파일")
                    QtWidgets.QMessageBox.information(
                        viewer,
                        "저장 완료 ✅",
                        f"워크플로우가 성공적으로 저장되었습니다!\n\n파일: {filename}\n형식: {file_type}\n노드 수: {len(result.get('steps', []))}개\n\n(워크플로우 파일에는 JSON과 첨부 파일들이 모두 포함됩니다.)"
                    )
                    print(f"✅ 저장 완료: {len(result.get('steps', []))}개의 노드가 저장되었습니다.")
                except Exception as e:
                    import traceback
                    error_msg = f"저장 중 오류가 발생했습니다:\n\n{str(e)}\n\n상세:\n{traceback.format_exc()}"
                    print(f"❌ 저장 오류: {error_msg}")
                    QtWidgets.QMessageBox.critical(
                        viewer,
                        "저장 오류 ❌",
                        error_msg
                    )
        except Exception as e:
            print(f"❌ 파일 다이얼로그 오류: {e}")
            QtWidgets.QMessageBox.critical(
                viewer,
                "오류",
                f"파일 저장 대화상자를 열 수 없습니다:\n{str(e)}"
            )
    
    # 툴바에 JSON 내보내기 버튼 추가
    try:
        # viewer가 QMainWindow인지 확인하고 툴바 추가
        from PySide2.QtWidgets import QMainWindow
        if isinstance(viewer, QMainWindow):
            toolbar = viewer.addToolBar("도구")
            export_btn = toolbar.addAction("💾 JSON 내보내기")
            export_btn.setToolTip("워크플로우를 파일로 저장합니다 (Ctrl+E)")
            export_btn.triggered.connect(on_export_json)
            print("✅ 툴바 버튼 추가 완료")
        # 툴바가 없어도 아래에서 메뉴바에 추가하므로 여기서는 추가하지 않음
    except Exception as e:
        print(f"⚠️ 버튼 추가 실패: {e}")
    
    # 키보드 단축키는 메뉴바의 QAction에서 설정하므로 여기서는 제거
    # (중복 등록 방지를 위해)
    
    # 메뉴바에 파일 메뉴 추가
    try:
        menu_bar = main_window.menuBar()
        if menu_bar:
            file_menu = menu_bar.addMenu("파일 (File)")
            
            # 새로 만들기
            new_action = file_menu.addAction("📄 새로 만들기 (Ctrl+N)")
            new_action.setShortcut("Ctrl+N")
            new_action.triggered.connect(on_new_workflow)
            new_action.setToolTip("새 워크플로우를 시작합니다")
            
            file_menu.addSeparator()
            
            # 파일 열기
            open_action = file_menu.addAction("📂 파일 열기 (Ctrl+O)")
            open_action.setShortcut("Ctrl+O")
            open_action.triggered.connect(on_open_json)
            open_action.setToolTip("저장된 워크플로우 JSON 파일을 불러옵니다")
            
            file_menu.addSeparator()
            
            # 파일 저장
            export_action = file_menu.addAction("💾 파일 저장 (Ctrl+E)")
            export_action.setShortcut("Ctrl+E")
            export_action.triggered.connect(on_export_json)
            export_action.setToolTip("워크플로우를 파일로 저장합니다 (Ctrl+E)")
            
            print("✅ 메뉴바에 파일 메뉴 추가 완료")
            
            # 편집 메뉴 추가
            edit_menu = menu_bar.addMenu("편집 (Edit)")
            
            # 복사
            copy_action = edit_menu.addAction("📋 복사 (Ctrl+C)")
            copy_action.setShortcut("Ctrl+C")
            copy_action.triggered.connect(on_copy_nodes)
            copy_action.setToolTip("선택된 노드를 복사합니다")
            
            # 붙여넣기
            paste_action = edit_menu.addAction("📄 붙여넣기 (Ctrl+V)")
            paste_action.setShortcut("Ctrl+V")
            paste_action.triggered.connect(on_paste_nodes)
            paste_action.setToolTip("복사된 노드를 붙여넣습니다")
            
            edit_menu.addSeparator()
            
            # 전체 선택
            select_all_action = edit_menu.addAction("전체 선택 (Ctrl+A)")
            select_all_action.setShortcut("Ctrl+A")
            select_all_action.triggered.connect(lambda: [n.set_selected(True) for n in graph.all_nodes()])
            select_all_action.setToolTip("모든 노드를 선택합니다")
            
            # 선택 해제
            deselect_action = edit_menu.addAction("선택 해제")
            deselect_action.triggered.connect(lambda: [n.set_selected(False) for n in graph.all_nodes()])
            deselect_action.setToolTip("모든 노드의 선택을 해제합니다")
            
            edit_menu.addSeparator()
            
            # 삭제
            delete_action = edit_menu.addAction("🗑️ 삭제 (Delete)")
            delete_action.setShortcut("Delete")
            delete_action.triggered.connect(lambda: [graph.delete_node(n) for n in graph.all_nodes() if n.selected()])
            delete_action.setToolTip("선택된 노드를 삭제합니다")
            
            print("✅ 메뉴바에 편집 메뉴 추가 완료")
            
            # 보기 메뉴 추가
            view_menu = menu_bar.addMenu("보기 (View)")
            
            # Fit to View - 모든 노드가 보이도록 줌
            fit_action = view_menu.addAction("🔍 전체 보기 (Fit to View) (Ctrl+F)")
            fit_action.setShortcut("Ctrl+F")
            fit_action.triggered.connect(fit_to_view)
            fit_action.setToolTip("모든 노드가 보이도록 적절한 배율로 줌합니다")
            
            print("✅ 메뉴바에 보기 메뉴 추가 완료")
    except Exception as e:
        print(f"⚠️ 메뉴바 추가 실패: {e}")
    
    # 6. 시작 메시지
    print("\n" + "="*60)
    print("🤖 AI 학습용 워크플로우 구조화 도구")
    print("="*60)
    print("📌 사용 방법:")
    print("   1. 좌측 패널의 버튼을 클릭하거나 그래프 영역에서 우클릭하여 노드를 추가하세요")
    print("   2. 노드를 드래그하여 연결하세요")
    print("   3. 노드를 클릭하여 속성을 편집하세요")
    print("   4. 파일 > 📂 파일 열기 (Ctrl+O)로 저장된 워크플로우를 불러오세요")
    print("   5. 파일 > 💾 파일 저장 (Ctrl+E)로 저장하세요")
    print("="*60 + "\n")

    sys.exit(app.exec_())