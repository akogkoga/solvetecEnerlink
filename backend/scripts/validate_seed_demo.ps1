$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$seedPath = Join-Path $root "data\seed_cnpjs.json"
$queriesPath = Join-Path $root "scripts\demo_queries.json"

$seed = Get-Content -Raw $seedPath | ConvertFrom-Json
$queries = Get-Content -Raw $queriesPath | ConvertFrom-Json
$companies = @($seed.companies)

function Normalize([string] $value) {
    if ($null -eq $value) { return "" }
    return $value.ToUpperInvariant()
}

function Match-Term($company, [string] $term) {
    if ([string]::IsNullOrWhiteSpace($term)) { return $true }
    $normalized = Normalize $term
    $aliases = @{
        "TECNOLOGIA" = @("TECNOLOGIA", "SOFTWARE", "INFORMATICA", "COMPUTADOR", "SISTEMAS")
        "MARKETING" = @("MARKETING", "PUBLICIDADE", "PROPAGANDA", "PROMOCAO", "AGENCIA")
        "CONTABILIDADE" = @("CONTABILIDADE", "CONTABIL", "AUDITORIA", "TRIBUTARIA")
        "MEI" = @("MEI", "MICROEMPREENDEDOR INDIVIDUAL", "EMPRESARIO INDIVIDUAL")
        "LTDA" = @("LTDA", "LIMITADA")
    }
    $needles = if ($aliases.ContainsKey($normalized)) { $aliases[$normalized] } else { @($normalized) }
    $text = Normalize "$($company.razao_social) $($company.nome_fantasia) $($company.cnae_fiscal_descricao) $($company.porte) $($company.natureza_juridica) $($company.termos)"
    foreach ($needle in $needles) {
        if ($text.Contains($needle)) { return $true }
    }
    return $false
}

function Match-Cnae($company, [string] $cnae) {
    if ([string]::IsNullOrWhiteSpace($cnae)) { return $true }
    $wanted = ($cnae -replace "\D", "")
    $prefix = if ($wanted.EndsWith("00") -and $wanted.Length -ge 4) { $wanted.Substring(0, $wanted.Length - 2) } else { $wanted }
    $code = [string]$company.cnae_fiscal
    if ($code.StartsWith($prefix) -or $code.Contains($wanted)) { return $true }
    foreach ($secondary in @($company.cnaes_secundarios)) {
        if ([string]$secondary.codigo -like "$prefix*") { return $true }
    }
    return $false
}

foreach ($query in $queries) {
    $payload = $query.payload
    $results = $companies | Where-Object {
        ($_.descricao_situacao_cadastral -like "*ATIVA*") -and
        ([string]::IsNullOrWhiteSpace($payload.estado) -or $_.uf -eq $payload.estado) -and
        ([string]::IsNullOrWhiteSpace($payload.cidade) -or (Normalize $_.municipio).Contains((Normalize $payload.cidade))) -and
        ([string]::IsNullOrWhiteSpace($payload.porte) -or (Normalize $_.porte).Contains((Normalize $payload.porte))) -and
        (Match-Cnae $_ $payload.cnae) -and
        (Match-Term $_ $payload.termo)
    }
    $count = @($results).Count
    $status = if ($count -gt 0) { "OK" } else { "VAZIO" }
    "{0,-32} {1,5} leads  {2}" -f $query.name, $count, $status
}
