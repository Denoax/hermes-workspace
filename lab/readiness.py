"""Stage requirements applied to observed native state, not operator enable flags."""
from dataclasses import dataclass

REQUIREMENTS = {
    'setup': ('kvm', 'root_storage_reserve', 'maintenance_idle'),
    'provision': ('kvm', 'runtime_packages', 'protected_supervisor', 'signed_base_image',
                  'installed_confinement', 'memory_reserve', 'maintenance_idle'),
    'qualify': ('owned_fleet_active', 'control_transport'),
    'normal': ('owned_fleet_active', 'control_transport', 'host_firewall_qualified',
               'VM_confinement_qualified', 'network_qualified', 'VM_watchdog_qualified',
               'guest_Hermes_installed', 'normal_backend_qualified', 'inference_window_active'),
    'paired': ('owned_fleet_active', 'control_transport', 'host_firewall_qualified',
               'VM_confinement_qualified', 'network_qualified', 'VM_watchdog_qualified',
               'guest_Hermes_installed', 'normal_backend_qualified', 'candidate_backend_qualified',
               'inference_window_active', 'Hermes_routing_qualified'),
    'workers': ('owned_fleet_active', 'control_transport', 'host_firewall_qualified',
                'VM_confinement_qualified', 'network_qualified', 'VM_watchdog_qualified',
                'Hermes_routing_qualified', 'tool_contracts_qualified', 'fresh_validation_guest'),
}


@dataclass(frozen=True)
class StageResult:
    stage: str
    ready: bool
    missing: tuple

    def as_dict(self):
        return {'ready': self.ready, 'missing': list(self.missing)}


def stage_results(observed):
    """Only the host inspector/native client supplies observed facts to this policy."""
    if type(observed) is not dict or any(type(value) is not bool for value in observed.values()):
        raise ValueError('invalid_observed_fact_types')
    return {name: StageResult(name, not (missing := tuple(key for key in keys if observed.get(key) is not True)), missing)
            for name, keys in REQUIREMENTS.items()}
