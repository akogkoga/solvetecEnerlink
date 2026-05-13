$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:ENERLINK_API_URL) { $env:ENERLINK_API_URL } else { "http://127.0.0.1:8000" }

$queries = @(
    @{ name = "Sao Paulo tecnologia"; payload = @{ termo = "tecnologia"; estado = "SP"; cidade = "Sao Paulo"; quantidade = 20 } },
    @{ name = "Sorocaba contabilidade"; payload = @{ termo = "contabilidade"; estado = "SP"; cidade = "Sorocaba"; quantidade = 20 } },
    @{ name = "Sao Paulo marketing"; payload = @{ termo = "marketing"; estado = "SP"; cidade = "Sao Paulo"; quantidade = 20 } },
    @{ name = "Sao Paulo LTDA"; payload = @{ termo = "LTDA"; estado = "SP"; cidade = "Sao Paulo"; natureza_juridica = "Limitada"; quantidade = 20 } },
    @{ name = "Sao Paulo ampla"; payload = @{ estado = "SP"; cidade = "Sao Paulo"; quantidade = 20 } },
    @{ name = "Rio de Janeiro tecnologia"; payload = @{ termo = "tecnologia"; estado = "RJ"; cidade = "Rio de Janeiro"; quantidade = 20 } },
    @{ name = "Minas Gerais mercados"; payload = @{ termo = "mercado"; estado = "MG"; quantidade = 20 } },
    @{ name = "Parana LTDA Curitiba"; payload = @{ termo = "LTDA"; estado = "PR"; cidade = "Curitiba"; quantidade = 20 } },
    @{ name = "Bahia restaurantes"; payload = @{ termo = "restaurante"; estado = "BA"; cidade = "Salvador"; quantidade = 20 } },
    @{ name = "Pernambuco MEI Recife"; payload = @{ termo = "MEI"; estado = "PE"; cidade = "Recife"; porte = "MEI"; quantidade = 20 } },
    @{ name = "Rio Grande do Sul clinicas"; payload = @{ termo = "clinica"; estado = "RS"; cidade = "Porto Alegre"; quantidade = 20 } }
)

foreach ($query in $queries) {
    $body = $query.payload | ConvertTo-Json -Compress
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $result = Invoke-RestMethod -Uri "$BaseUrl/api/v1/leads/generate" -Method POST -ContentType "application/json" -Body $body
    $watch.Stop()
    $providers = $result.providers_used -join ","
    $top = if (@($result.leads).Count -gt 0) { $result.leads[0].empresa } else { "-" }
    $status = if ($result.total_returned -gt 0) { "OK" } else { "VAZIO" }
    "{0,-32} returned={1,4} found={2,4} api_ms={3,5} wall_ms={4,5} providers={5,-28} {6} top={7}" -f `
        $query.name, $result.total_returned, $result.total_found, $result.search_time_ms, $watch.ElapsedMilliseconds, $providers, $status, $top
}
