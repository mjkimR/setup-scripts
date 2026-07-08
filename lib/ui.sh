#!/usr/bin/env bash

# Bash 멀티 셀렉트 메뉴 (TUI)
# Usage:
#   source lib/ui.sh
#   options=("Option 1" "Option 2" "Option 3")
#   defaults=(true false true)
#   multi_select_menu "설치할 도구들을 선택하세요:" options defaults selected_results
#   # selected_results 배열에 "0" "2" 와 같이 선택된 인덱스가 들어옵니다.

multi_select_menu() {
  local prompt="$1"
  local -n menu_options="$2"
  local -n menu_defaults="$3"
  local -n menu_out_array="$4"

  local num_options=${#menu_options[@]}
  local active_idx=0
  local -a checked

  # 초기 체크 상태 설정
  for ((i=0; i<num_options; i++)); do
    if [ "${menu_defaults[i]}" = "true" ]; then
      checked[i]=true
    else
      checked[i]=false
    fi
  done

  # 터미널 설정 저장 및 커서 숨김, 키 반향 끔
  local term_state
  term_state=$(stty -g)
  tput civis # 커서 숨김
  stty -echo

  # 스크립트 도중 Ctrl+C 등으로 종료 시 터미널 복구하도록 트랩 설정
  cleanup_ui() {
    stty "$term_state"
    tput cnorm # 커서 보임
  }
  trap 'cleanup_ui; exit 1' INT TERM

  # 화면 렌더링 함수
  draw_menu() {
    # 프롬프트 출력
    printf "\n\033[1;36m%s\033[0m (Arrow keys: Navigate, Space: Select/Deselect, Enter: Confirm)\n" "$prompt"
    for ((i=0; i<num_options; i++)); do
      local checkbox="[ ]"
      if [ "${checked[i]}" = "true" ]; then
        checkbox="[\033[1;32m✓\033[0m]"
      fi

      if [ $i -eq $active_idx ]; then
        # 현재 활성화된 줄 (화살표 포커스)
        printf " \033[1;33m➔\033[0m %b %b\n" "$checkbox" "\033[1;33m${menu_options[i]}\033[0m"
      else
        printf "   %b %s\n" "$checkbox" "${menu_options[i]}"
      fi
    done
  }

  # 메뉴 초기 렌더링
  draw_menu

  # 키 입력 감지 루프
  while true; do
    # 1바이트 키 입력 대기
    read -rsn1 key
    
    # 이스케이프 시퀀스 처리 (방향키)
    if [[ "$key" == $'\x1b' ]]; then
      read -rsn2 -t 0.05 key
      if [[ "$key" == "[A" ]]; then # 위 화살표
        ((active_idx--))
        if [ $active_idx -lt 0 ]; then
          active_idx=$((num_options - 1))
        fi
      elif [[ "$key" == "[B" ]]; then # 아래 화살표
        ((active_idx++))
        if [ $active_idx -ge $num_options ]; then
          active_idx=0
        fi
      fi
    elif [[ "$key" == "" ]]; then # 엔터
      break
    elif [[ "$key" == " " ]]; then # 스페이스바
      if [ "${checked[active_idx]}" = "true" ]; then
        checked[active_idx]=false
      else
        checked[active_idx]=true
      fi
    fi

    # 이전 출력 화면 지우기 (num_options + 2 라인만큼 위로 커서 이동 후 청소)
    local lines_to_clear=$((num_options + 2))
    for ((i=0; i<lines_to_clear; i++)); do
      printf "\033[A\033[K"
    done

    draw_menu
  done

  # UI 복구
  cleanup_ui
  trap - INT TERM

  # 최종 선택된 인덱스 반환
  menu_out_array=()
  for ((i=0; i<num_options; i++)); do
    if [ "${checked[i]}" = "true" ]; then
      menu_out_array+=("$i")
    fi
  done
  printf "\n"
}
