function stack-file-backup --description 'Create a .bak copy of a file' --argument filename
    cp $filename $filename.bak
end
