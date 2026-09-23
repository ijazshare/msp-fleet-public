# Exec seat shell. Red prompt; the gate verbs are plain commands.
[ -f /etc/bash.bashrc ] && . /etc/bash.bashrc
[ -f ~/.bashrc ] && . ~/.bashrc
PS1='\[\e[1;41;97m\] EXEC \[\e[0m\]\[\e[1;31m\] \u@\h:\w# \[\e[0m\]'
step()    { /usr/local/sbin/msp-gate step; }
pending() { /usr/local/sbin/msp-gate pending; }
pause()   { /usr/local/bin/msp-rec pause; }
resume()  { /usr/local/bin/msp-rec resume; }
