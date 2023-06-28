#!/bin/bash

find_conda_exe() {
    local -n _conda_exe=$1

    rm -f $tmp_file

    # Hard-coded paths to Github miniconda
    local conda_dirs=$( \
      find /home/runner -type d -exec test -x {}/conda -a -e {}/activate \; -print 2> /dev/null || \
      find ~/.conda -type d -exec test -x {}/conda -a -e {}/activate \; -print 2> /dev/null && \
      find /opt/conda/bin -type d -exec test -x {}/conda -a -e {}/activate \; -print 2> /dev/null && \
      find /usr/local -type d -exec test -x {}/conda -a -e {}/activate \; -print 2> /dev/null && \
      find /root/*conda -type d -exec test -x {}/conda -a -e {}/activate \; -print 2> /dev/null \
      )

    local selected_version="0.0.0"
    local selected_conda_exe=""

    if [ "${_conda_exe} " != " " ]; then
      selected_version=$(${_conda_exe} info --json 2>/dev/null | jq -r '.conda_version')
      selected_conda_exe=${_conda_exe}
    else
      selected_conda_exe=$(which conda 2>/dev/null)
      if [ "${selected_conda_exe}_" != "_" ]; then
        selected_version=$(${selected_conda_exe} info --json 2>/dev/null | jq -r '.conda_version')
      fi
    fi

    # Finding the latest version of conda
    echo -n "   " >&2
    for c in ${conda_dirs}; do
      echo -n "." >&2
      current_version=$(${c}/conda info --json 2>/dev/null | jq -r --arg version $selected_version '
        .conda_version | split(".") | map(tonumber) as $current_version
        | ($version | split(".") | map(tonumber)) as $version
        | (if $current_version > $version then
            $current_version
          else
            empty
          end) as $selected_version
        | $selected_version | join(".")
      ')

      if [ "${current_version}_" != "_" ]; then
        selected_conda_exe=${c}/conda
        selected_version=${current_version}
      fi
    done
    echo "." >&2

    _conda_exe=${selected_conda_exe}

    if [ "${_conda_exe}_" == "_" ]; then
        echo "Please install Anaconda w/ Python 3.10+ first"
        echo "See: https://www.anaconda.com/distribution/"
        exit 1
    fi

    echo "Selected: ${selected_conda_exe}" >&2
}

get_env_file() {
    local env_file=$1

    cd $(dirname $PWD/${env_file})
    local env_ext="${env_file##*.}"

    echo "Available environments:" >&2
    local files=( $(find . -type f -name "*.${env_ext}" -printf '%f\n' | tac) )
    local i=1
    for file in "${files[@]}"; do
        echo "   ${i}: ${file}" >&2
        i=$((i+1))
    done

    local user_input
    while true; do
        read -t 10 -p "Enter your choice [1-${#files[@]}]: " user_input
        if [ "${user_input}_" == "_" ]; then
            echo ${files[0]}
            return
        fi
        if [[ ${user_input} -ge 1 && ${user_input} -le ${#files[@]} ]]; then
            break
        else
            echo "Invalid selection. Please enter a number between 1 and ${#files[@]}." >&2
        fi
    done

    echo ${files[$((user_input-1))]}
}

get_env_name() {
    local env_file=$1

    cd $(dirname $PWD/${env_file})

    local valid_env_name=$(grep  'name:' ${env_file} | tail -n1 | awk '{ print $2}')
    local response
    read -t 10 -p "Enter environment name [${valid_env_name}](10s wait): " response
    if [ "${response}_" == "_" ]; then
        response=${valid_env_name}
    fi

    echo ${response}
}

check_env_name() {
  local conda_exe="$1"
  local env_file="$2"
  local conda_agent="$3"
  local valid_env_name
  valid_env_name=$(grep  'name:' "${env_file}" | tail -n1 | awk '{ print $2}')
  read -t 30 -p "Enter environment name [${valid_env_name}](30s wait): " response
  if [ "${response}_" == "_" ]; then
    echo ""
    echo "  -> Using default environment name: ${valid_env_name}"
    echo "                   environment file: ${env_file}"
    echo "                   Conda user_agent: ${conda_agent}"
    response=${valid_env_name}
  fi

  local env_name="${response}"

  if [ "$env_name" != "$valid_env_name" ]; then
    echo "*** Incompatible environment name in ${env_file} (${valid_env_name}). Please resolve and try again."
    exit 1
  fi
}

verify_pip_packages() {
  echo "  '-> Verifying conda alternative to pip packages" >&2
  local install_dir="/tmp/hb_install"
  rm -rf $install_dir
  mkdir -p $install_dir
  while read package; do
    package_name=$(echo $package | cut -d'=' -f1)
    package_version=$(echo $package | cut -d'=' -f3)
    echo "      Searching for $package_name:$package_version" >&2
    conda search --json $package_name | jq -r --arg pkg "$package_name" --arg ver "$package_version" '
      if .[$pkg] == null or (.[$pkg] | map(has("version")) | all(false)) then
        | empty
      else
        .[$pkg][] | select(.version) | .version  as $version
        | ($version | split(".") | map(tonumber)) as $arrayed_version
        | ($ver | split(".") | map(tonumber)) as $arrayed_ver
        |  (if $arrayed_version >= $arrayed_ver then
            $pkg + "==" + $version
          else
            empty
          end) as $selected_version
        | $selected_version
        | halt_error
        | .name + "=" + .version
      end
    ' 2>> $install_dir/conda_package_list.txt
    echo | cat >> $install_dir/conda_package_list.txt
  done < setup/pip_packages.txt
  grep -v -f <(cut -d '=' -f1 $install_dir/conda_package_list.txt) setup/pip_packages.txt 2> $install_dir/updated_pip_packages.txt
}
