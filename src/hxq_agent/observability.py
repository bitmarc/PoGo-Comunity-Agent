"""Telemetria: traces, metricas y logs hacia Application Insights.

MAF ya emite OpenTelemetry nativo (spans por turno, por llamada a tool y por peticion al
modelo). Aqui solo se le dice donde exportarlo. Los providers los configura MAF, no el
distro de Azure Monitor: si ambos los configuran, se pelean.

Sin `APPLICATIONINSIGHTS_CONNECTION_STRING` no se activa nada. En local no hace falta.
"""

from __future__ import annotations

import logging

from hxq_agent.config import Settings, get_settings

logger = logging.getLogger(__name__)

_configurado = False


def configurar_telemetria(settings: Settings | None = None) -> bool:
    """Engancha los exportadores de Azure Monitor a la instrumentacion de MAF.

    Devuelve True si quedo activa. Idempotente: llamarla dos veces no duplica spans.
    """
    global _configurado
    if _configurado:
        return True

    settings = settings or get_settings()
    conexion = settings.applicationinsights_connection_string.strip()
    if not conexion:
        logger.info("Telemetria desactivada (sin APPLICATIONINSIGHTS_CONNECTION_STRING)")
        return False

    try:
        from agent_framework.observability import configure_otel_providers, enable_instrumentation
        from azure.monitor.opentelemetry.exporter import (
            AzureMonitorLogExporter,
            AzureMonitorMetricExporter,
            AzureMonitorTraceExporter,
        )

        configure_otel_providers(
            service_name="hxq-agent",
            exporters=[
                AzureMonitorTraceExporter(connection_string=conexion),
                AzureMonitorMetricExporter(connection_string=conexion),
                AzureMonitorLogExporter(connection_string=conexion),
            ],
            # Los prompts y respuestas NO se exportan: llevan contenido de la comunidad y
            # no hay razon para tenerlos en telemetria. Se activa solo para depurar.
            enable_sensitive_data=settings.hxq_telemetry_sensitive,
        )
        enable_instrumentation()
    except Exception:
        # Que falle la telemetria nunca debe impedir que la app arranque.
        logger.exception("No se pudo configurar la telemetria; la app sigue sin ella")
        return False

    _configurado = True
    logger.info(
        "Telemetria activa hacia Application Insights (datos sensibles: %s)",
        "SI" if settings.hxq_telemetry_sensitive else "no",
    )
    return True
