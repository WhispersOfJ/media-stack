function stack-claude-home --description 'Launch Claude in the ~/Claude workspace with full permissions'
    cd /home/bear/Claude && claude --dangerously-skip-permissions --add-dir /home/bear/Claude $argv
end
