function stack-tmdb-audit --description 'Audit TMDB links in a Plex library (Movies by default)'
    cd $HOME/Claude/media-stack && python3 scripts/audit-tmdb-links.py --library Movies --csv /tmp/tmdb_audit_movies.csv $argv
end
