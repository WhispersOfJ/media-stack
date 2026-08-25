function stack-cleanuparr-instances --description 'Which *arr apps Cleanuparr has an actual connected instance for'
    __stack_api GET /api/v2/cleanuparr/instances
end
