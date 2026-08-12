# Usage: stack-scrutiny-summary
# All-disk SMART status at a glance: model, temperature, power-on hours, and
# whether Scrutiny considers each device healthy. Complements
# stack-disk-health (raw smartctl right now) with Scrutiny's trended view.
function stack-scrutiny-summary --description 'All-disk SMART status at a glance'
    __stack_api GET /api/scrutiny/summary
end
