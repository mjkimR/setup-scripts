#!/usr/bin/env bash

# Bash Multi-select Menu (TUI)
# Usage:
#   source lib/ui.sh
#   options=("Option 1" "Option 2" "Option 3")
#   defaults=(true false true)
#   multi_select_menu "Select tools to install:" options defaults selected_results
#   # Outputs selected indices (e.g. "0" "2") into selected_results array.

multi_select_menu() {
  local prompt="$1"
  # Stock macOS ships bash 3.2, which has no `local -n` namerefs — the caller's
  # arrays are copied in through eval and the result written back the same way.
  # The _msm_ prefix keeps these locals from shadowing the caller's array names.
  local _msm_options_name="$2"
  local _msm_defaults_name="$3"
  local _msm_out_name="$4"
  local -a _msm_options=()
  local -a _msm_defaults=()
  eval "_msm_options=(\"\${${_msm_options_name}[@]}\")"
  eval "_msm_defaults=(\"\${${_msm_defaults_name}[@]}\")"

  local num_options=${#_msm_options[@]}
  local active_idx=0
  local -a checked

  # Set initial check state
  for ((i=0; i<num_options; i++)); do
    if [ "${_msm_defaults[i]}" = "true" ]; then
      checked[i]=true
    else
      checked[i]=false
    fi
  done

  # Save terminal state, hide cursor, and turn off echo
  local term_state
  term_state=$(stty -g)
  tput civis # Hide cursor
  stty -echo

  # Restore terminal configuration on script exit (Ctrl+C, termination)
  cleanup_ui() {
    stty "$term_state"
    tput cnorm # Show cursor
  }
  trap 'cleanup_ui; exit 1' INT TERM

  # Screen rendering function
  draw_menu() {
    # Print prompt
    printf "\n\033[1;36m%s\033[0m (Arrow keys: Navigate, Space: Select/Deselect, Enter: Confirm)\n" "$prompt"
    for ((i=0; i<num_options; i++)); do
      local checkbox="[ ]"
      if [ "${checked[i]}" = "true" ]; then
        checkbox="[\033[1;32m✓\033[0m]"
      fi

      if [ $i -eq $active_idx ]; then
        # Currently active option (Arrow focus)
        printf " \033[1;33m➔\033[0m %b %b\n" "$checkbox" "\033[1;33m${_msm_options[i]}\033[0m"
      else
        printf "   %b %s\n" "$checkbox" "${_msm_options[i]}"
      fi
    done
  }

  # Initial menu rendering
  draw_menu

  # Key input detection loop
  while true; do
    # Wait for 1-byte key input. IFS= matters: without it read strips a lone
    # space to "", which is indistinguishable from Enter — spacebar would
    # confirm the menu instead of toggling.
    IFS= read -rsn1 key
    
    # Handle escape sequences (Arrow keys)
    if [[ "$key" == $'\x1b' ]]; then
      # bash 3.2 rejects fractional read timeouts; the [A/[B bytes of an arrow
      # key arrive instantly anyway, so a 1s ceiling only affects a bare ESC.
      IFS= read -rsn2 -t 1 key
      if [[ "$key" == "[A" ]]; then # Up arrow
        ((active_idx--))
        if [ $active_idx -lt 0 ]; then
          active_idx=$((num_options - 1))
        fi
      elif [[ "$key" == "[B" ]]; then # Down arrow
        ((active_idx++))
        if [ $active_idx -ge $num_options ]; then
          active_idx=0
        fi
      fi
    elif [[ "$key" == "" ]]; then # Enter
      break
    elif [[ "$key" == " " ]]; then # Spacebar
      if [ "${checked[active_idx]}" = "true" ]; then
        checked[active_idx]=false
      else
        checked[active_idx]=true
      fi
    fi

    # Clear previous output (move cursor up by num_options + 2 lines and clear)
    local lines_to_clear=$((num_options + 2))
    for ((i=0; i<lines_to_clear; i++)); do
      printf "\033[A\033[K"
    done

    draw_menu
  done

  # Restore UI
  cleanup_ui
  trap - INT TERM

  # Return final selected indices
  eval "${_msm_out_name}=()"
  for ((i=0; i<num_options; i++)); do
    if [ "${checked[i]}" = "true" ]; then
      eval "${_msm_out_name}+=(\"$i\")"
    fi
  done
  printf "\n"
}
