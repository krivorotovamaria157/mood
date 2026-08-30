$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$repo = 'C:\Users\elman\repositories\mood'
$Xlsx = (Get-ChildItem "$repo\*.xlsx" | Where-Object { $_.Name -ne 'backup_original.xlsx' } | Select-Object -First 1).FullName
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("xlsxfix_" + [System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Force -Path $work | Out-Null
[System.IO.Compression.ZipFile]::ExtractToDirectory($Xlsx, $work)

$NSM = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
$utf8 = New-Object System.Text.UTF8Encoding($true)

function Read-Part([string]$rel) { [System.IO.File]::ReadAllText((Join-Path $work $rel), [System.Text.Encoding]::UTF8) }
function Write-Part([string]$rel, [string]$text) { [System.IO.File]::WriteAllText((Join-Path $work $rel), $text, $utf8) }

# --- regex-based cell replacement (cells never nest) -------------------------
function Replace-Cell([string]$xml, [string]$ref, [string]$newCell) {
  $re = '<c r="' + $ref + '"(?:\s[^>]*)?(?:/>|>.*?</c>)'
  $m = [regex]::Match($xml, $re, [Text.RegularExpressions.RegexOptions]::Singleline)
  if (-not $m.Success) { throw "cell $ref not found" }
  return $xml.Remove($m.Index, $m.Length).Insert($m.Index, $newCell)
}

function Col-Num([string]$col) {
  $n = 0; foreach ($ch in $col.ToCharArray()) { $n = $n * 26 + ([int][char]$ch - 64) }; return $n
}

# --- DOM helpers -------------------------------------------------------------
function Get-Doc([string]$rel) {
  $d = New-Object System.Xml.XmlDocument
  $d.PreserveWhitespace = $true
  $d.Load((Join-Path $work $rel))
  return ,$d
}
function Save-Doc($doc, [string]$rel) {
  $ws = New-Object System.Xml.XmlWriterSettings
  $ws.Encoding = $utf8; $ws.Indent = $false; $ws.OmitXmlDeclaration = $false
  $w = [System.Xml.XmlWriter]::Create((Join-Path $work $rel), $ws)
  $doc.Save($w); $w.Close()
}
function Nsm($doc) {
  $n = New-Object System.Xml.XmlNamespaceManager($doc.NameTable)
  $n.AddNamespace('m', $NSM); return ,$n
}

# Insert or replace a cell inside a sheetData row, preserving column order.
function Set-CellDom($doc, $nsMgr, [string]$ref, [string]$style, [string]$type, [string]$inner) {
  $mm = [regex]::Match($ref, '^([A-Z]+)(\d+)$')
  $col = $mm.Groups[1].Value; $rowNum = [int]$mm.Groups[2].Value
  $sheetData = $doc.psbase.SelectSingleNode('//m:sheetData', $nsMgr)
  $row = $doc.psbase.SelectSingleNode("//m:sheetData/m:row[@r='$rowNum']", $nsMgr)
  if (-not $row) {
    $row = $doc.CreateElement('row', $NSM); $row.SetAttribute('r', "$rowNum")
    $after = $null
    foreach ($r in $sheetData.psbase.SelectNodes('m:row', $nsMgr)) { if ([int]$r.GetAttribute('r') -lt $rowNum) { $after = $r } }
    if ($after) { [void]$sheetData.psbase.InsertAfter($row, $after) } else { [void]$sheetData.psbase.PrependChild($row) }
  }
  $cell = $row.psbase.SelectSingleNode("m:c[@r='$ref']", $nsMgr)
  if (-not $cell) {
    $cell = $doc.CreateElement('c', $NSM); $cell.SetAttribute('r', $ref)
    $target = Col-Num $col; $after = $null
    foreach ($c in $row.psbase.SelectNodes('m:c', $nsMgr)) {
      $cr = [regex]::Match($c.GetAttribute('r'), '^([A-Z]+)').Groups[1].Value
      if ((Col-Num $cr) -lt $target) { $after = $c }
    }
    if ($after) { [void]$row.psbase.InsertAfter($cell, $after) } else { [void]$row.psbase.PrependChild($cell) }
  }
  $cell.psbase.RemoveAll(); $cell.SetAttribute('r', $ref)
  if ($style) { $cell.SetAttribute('s', $style) }
  if ($type)  { $cell.SetAttribute('t', $type) }
  if ($inner) { $cell.InnerXml = $inner -replace '<f>', "<f xmlns=`"$NSM`">" -replace '<is>', "<is xmlns=`"$NSM`">" -replace '<v>', "<v xmlns=`"$NSM`">" }
}

$log = New-Object System.Collections.Generic.List[string]
function Note($s) { $log.Add($s); Write-Output $s }

# =============================================================================
# ЭТАП 1 — очистка листа «Данные» (sheet3)
# =============================================================================
$d3 = Get-Doc 'xl\worksheets\sheet3.xml'
$n3 = Nsm $d3
$sd = $d3.psbase.SelectSingleNode('//m:sheetData', $n3)
$removed = 0
foreach ($r in @($sd.psbase.SelectNodes('m:row', $n3))) {
  if ([int]$r.GetAttribute('r') -ge 12) { [void]$sd.psbase.RemoveChild($r); $removed++ }
}
$d3.psbase.SelectSingleNode('//m:dimension', $n3).SetAttribute('ref', 'A1:R11')
Save-Doc $d3 'xl\worksheets\sheet3.xml'
Note "Этап 1: удалено строк из «Данные» = $removed (осталось 10 записей, строки 2-11)"

# =============================================================================
# ЭТАП 5 — контроль ввода в «Данные» (правится тот же лист, строкой)
# =============================================================================
$s3 = Read-Part 'xl\worksheets\sheet3.xml'

$cf = '<conditionalFormatting sqref="G2:G1000">' +
      '<cfRule type="cellIs" dxfId="0" priority="10" operator="equal"><formula>"+"</formula></cfRule>' +
      '<cfRule type="cellIs" dxfId="1" priority="11" operator="equal"><formula>"-"</formula></cfRule>' +
      '</conditionalFormatting>'

$dvNum = {
  param($sqref, $type, $lo, $hi, $title, $msg)
  '<dataValidation type="' + $type + '" operator="between" allowBlank="1" showInputMessage="1" showErrorMessage="1"' +
  ' errorTitle="' + $title + '" error="' + $msg + '" sqref="' + $sqref + '">' +
  '<formula1>' + $lo + '</formula1><formula2>' + $hi + '</formula2></dataValidation>'
}
$dv = '<dataValidations count="5">' +
      '<dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="R2:R1000"><formula1>"Да,Нет"</formula1></dataValidation>' +
      (& $dvNum 'F2:F1000' 'whole' 1 10 'Интенсивность' 'Введите целое число от 1 до 10.') +
      (& $dvNum 'L2:L1000 M2:M1000' 'whole' 1 10 'Уровень энергии' 'Введите целое число от 1 до 10.') +
      (& $dvNum 'P2:P1000' 'whole' 1 10 'Самооценка' 'Введите целое число от 1 до 10.') +
      (& $dvNum 'Q2:Q1000' 'decimal' 0 24 'Сон (часы)' 'Введите число от 0 до 24.') +
      '</dataValidations>'

$s3 = [regex]::Replace($s3, '<dataValidations count="1">.*?</dataValidations>', ($cf + $dv), [Text.RegularExpressions.RegexOptions]::Singleline)

$x14 = {
  param($src, $sqref)
  '<x14:dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1">' +
  '<x14:formula1><xm:f>' + $src + '</xm:f></x14:formula1><xm:sqref>' + $sqref + '</xm:sqref></x14:dataValidation>'
}
$ext = '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}" xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main">' +
       '<x14:dataValidations count="6" xmlns:xm="http://schemas.microsoft.com/office/excel/2006/main">' +
       (& $x14 'Справочники!$A$2:$A$50' 'D2:D1000') +
       (& $x14 'Справочники!$A$2:$A$50' 'E2:E1000') +
       (& $x14 'Справочники!$C$2:$C$36' 'H2:H1000') +
       (& $x14 'Справочники!$B$2:$B$16' 'I2:I1000') +
       (& $x14 'Аналитика!$S$2:$S$14'   'N2:N1000') +
       (& $x14 'Справочники!$D$2:$D$4'  'O2:O1000') +
       '</x14:dataValidations></ext></extLst>'
$s3 = [regex]::Replace($s3, '<extLst>.*?</extLst>', $ext, [Text.RegularExpressions.RegexOptions]::Singleline)
Write-Part 'xl\worksheets\sheet3.xml' $s3
Note "Этап 5: 5 плоских проверок + 6 списочных (x14) + условное форматирование G2:G1000"

# styles.xml — два dxf для валентности
$st = Read-Part 'xl\styles.xml'
$dxfs = '<dxfs count="2">' +
        '<dxf><font><color rgb="FF006100"/></font><fill><patternFill><bgColor rgb="FFC6EFCE"/></patternFill></fill></dxf>' +
        '<dxf><font><color rgb="FF9C0006"/></font><fill><patternFill><bgColor rgb="FFFFC7CE"/></patternFill></fill></dxf>' +
        '</dxfs>'
$st = $st -replace '<dxfs count="0"\s*/>', $dxfs
Write-Part 'xl\styles.xml' $st
Note "Этап 5: в styles.xml добавлены 2 dxf (зелёный «+», красный «-»)"

# =============================================================================
# ЭТАП 2 — «Справочники» (sheet2): дубль «Тоска» и опечатка
# =============================================================================
$d2 = Get-Doc 'xl\worksheets\sheet2.xml'
$n2 = Nsm $d2
$snap = @{}
foreach ($rn in 22..51) {
  foreach ($col in @('A', 'G')) {
    $c = $d2.psbase.SelectSingleNode("//m:sheetData/m:row[@r='$rn']/m:c[@r='$col$rn']", $n2)
    if ($c) { $snap["$col$rn"] = @{ s = $c.GetAttribute('s'); t = $c.GetAttribute('t'); inner = $c.InnerXml } }
  }
}
# развёрнутая рекомендация про тоску переезжает в единственную оставшуюся строку «Тоска»
Set-CellDom $d2 $n2 'G22' $snap['G33'].s $snap['G33'].t $snap['G33'].inner
$row22 = $d2.psbase.SelectSingleNode("//m:sheetData/m:row[@r='22']", $n2)
$row22.SetAttribute('ht', '187.2'); $row22.SetAttribute('customHeight', '1')
# сдвиг списка эмоций и рекомендаций на строку вверх
foreach ($rn in 33..50) {
  foreach ($col in @('A', 'G')) {
    $src = $snap["$col$([int]$rn + 1)"]
    Set-CellDom $d2 $n2 "$col$rn" $src.s $src.t $src.inner
  }
}
Set-CellDom $d2 $n2 'A50' $snap['A51'].s 'inlineStr' '<is><t>Умиротворение</t></is>'
Set-CellDom $d2 $n2 'A51' $snap['A51'].s '' ''
Set-CellDom $d2 $n2 'G51' $snap['G51'].s '' ''
$d2.psbase.SelectSingleNode('//m:dimension', $n2).SetAttribute('ref', 'A1:G51')
Save-Doc $d2 'xl\worksheets\sheet2.xml'
Note "Этап 2: убран дубль «Тоска» (A33), список сдвинут в A2:A50, исправлено «Умиртворение» -> «Умиротворение»"

# =============================================================================
# ЭТАП 4 — «Аналитика» (sheet6)
# =============================================================================
$d6 = Get-Doc 'xl\worksheets\sheet6.xml'
$n6 = Nsm $d6

Set-CellDom $d6 $n6 'B7' '20' '' '<f>COUNTIF(Данные!G:G,"+")/(COUNTIF(Данные!G:G,"+")+COUNTIF(Данные!G:G,"-"))*100</f>'
Set-CellDom $d6 $n6 'E31' '4' '' '<f>COUNTIF(Данные!D:D,"Умиротворение")</f>'
Set-CellDom $d6 $n6 'E32' '4' '' '<f>COUNTIF(Данные!D:D,"Сожаление")</f>'

# строка 33 — «Разочарование» (записи есть в «Данных», строки в блоке не было)
Set-CellDom $d6 $n6 'D33' '4' 'inlineStr' '<is><t>Разочарование</t></is>'
Set-CellDom $d6 $n6 'E33' '4' '' '<f>COUNTIF(Данные!D:D,"Разочарование")</f>'
Set-CellDom $d6 $n6 'F33' '22' '' '<f t="shared" si="0"/>'
# «ВСЕГО» переезжает на строку 34 и охватывает весь блок
Set-CellDom $d6 $n6 'D34' '4' 's' '<v>278</v>'
Set-CellDom $d6 $n6 'E34' '4' '' '<f>SUM(E3:E33)</f>'
Set-CellDom $d6 $n6 'F34' '22' '' '<f>SUM(F3:F33)</f>'

# Y2:Y5 — снять #ДЕЛ/0!
$parts = @{ 'Y2' = 'Утро'; 'Y3' = 'День'; 'Y4' = 'Вечер'; 'Y5' = 'Ночь' }
foreach ($k in $parts.Keys) {
  Set-CellDom $d6 $n6 $k '4' '' ('<f>IFERROR(AVERAGEIF(Дневник!C:C,"' + $parts[$k] + '",Дневник!H:H),"")</f>')
}

# служебный столбец W — ранжирование способов совладания при равных процентах
Set-CellDom $d6 $n6 'W1' '18' 'inlineStr' '<is><t>Ранг способа (служебное)</t></is>'
foreach ($rn in 2..14) {
  Set-CellDom $d6 $n6 "W$rn" '4' '' ("<f>IF(T$rn=0,`"`",V$rn-ROW()/100000)</f>")
}
# служебный столбец AB — ранжирование эмоций при равных частотах
Set-CellDom $d6 $n6 'AB2' '21' 'inlineStr' '<is><t>Ранг эмоции (служебное)</t></is>'
foreach ($rn in 3..33) {
  Set-CellDom $d6 $n6 "AB$rn" '4' '' ("<f>E$rn-ROW()/100000</f>")
}
$d6.psbase.SelectSingleNode('//m:dimension', $n6).SetAttribute('ref', 'A1:AB35')
Save-Doc $d6 'xl\worksheets\sheet6.xml'

# общая формула доли: делитель $E$33 -> $E$34, диапазон F3:F32 -> F3:F33
$s6 = Read-Part 'xl\worksheets\sheet6.xml'
$before = $s6
$s6 = $s6.Replace('<f t="shared" ref="F3:F32" si="0">E3/$E$33*100</f>', '<f t="shared" ref="F3:F33" si="0">E3/$E$34*100</f>')
if ($s6 -eq $before) { throw 'общая формула F3 не найдена' }
Write-Part 'xl\worksheets\sheet6.xml' $s6
Note "Этап 4: E31/E32 исправлены, добавлено «Разочарование» (стр.33), ВСЕГО -> стр.34 (SUM E3:E33), индекс тонуса приведён к 0-100, Y2:Y5 в IFERROR, добавлены служебные столбцы W и AB"

# chart1 — охватить весь блок эмоций
$c1 = Read-Part 'xl\charts\chart1.xml'
$c1 = $c1.Replace('Аналитика!$D$3:$D$31', 'Аналитика!$D$3:$D$33').Replace('Аналитика!$E$3:$E$31', 'Аналитика!$E$3:$E$33')
Write-Part 'xl\charts\chart1.xml' $c1
Note "Этап 4: chart1 «Мои Эмоции» расширен до D3:D33 / E3:E33"

# =============================================================================
# ЭТАП 3 — «Инсайты» (sheet5)
# =============================================================================
$s5 = Read-Part 'xl\worksheets\sheet5.xml'
$AB = 'Аналитика!$AB$3:$AB$33'
$DD = 'Аналитика!$D$3:$D$33'
$EE = 'Аналитика!$E$3:$E$33'
$W  = 'Аналитика!$W$2:$W$14'

# сдвиг ссылок на «Аналитику»
$s5 = Replace-Cell $s5 'B3'  '<c r="B3" s="32"><f>Аналитика!B2</f></c>'
$s5 = Replace-Cell $s5 'B5'  '<c r="B5" s="32"><f>Аналитика!B4</f></c>'
$s5 = Replace-Cell $s5 'B6'  '<c r="B6" s="32"><f>Аналитика!B5</f></c>'
$s5 = Replace-Cell $s5 'B7'  '<c r="B7" s="32"><f>Аналитика!B6</f></c>'
$s5 = Replace-Cell $s5 'B12' '<c r="B12" s="5"><f>Аналитика!B7</f></c>'
# период наблюдения — датами, а не порядковыми номерами
$s5 = Replace-Cell $s5 'B4'  ('<c r="B4" s="32"><f>TEXT(MIN(Данные!A:A),"ДД.ММ.ГГГГ")&amp;" — "&amp;TEXT(MAX(Данные!A:A),"ДД.ММ.ГГГГ")</f></c>')
# преобладающая эмоция и ТОП-3 — с разрешением равных частот
$pick = "INDEX($DD,MATCH(MAX($AB),$AB,0))"
$s5 = Replace-Cell $s5 'B13' ('<c r="B13" s="5"><f>' + $pick + '</f></c>')
$s5 = Replace-Cell $s5 'B46' ('<c r="B46" s="32"><f>' + $pick + '</f></c>')
foreach ($k in 1..3) {
  $ref = "B$(12 + $k + 1)"
  $st2 = if ($k -eq 3) { '34' } else { '5' }
  $f = "IFERROR(INDEX($EE,MATCH(LARGE($AB,$k),$AB,0))&amp;`" — `"&amp;INDEX($DD,MATCH(LARGE($AB,$k),$AB,0)),`"—`")"
  $s5 = Replace-Cell $s5 $ref ('<c r="' + $ref + '" s="' + $st2 + '"><f>' + $f + '</f></c>')
}
# ТОП-5 способов совладания — по служебному рангу, без повторов
foreach ($k in 1..5) {
  $rowN = 32 + $k
  $sB = if ($k -eq 5) { '34' } else { '5' }
  $sD = if ($k -eq 5) { '38' } elseif ($k -eq 1) { '36' } else { '37' }
  $fB = "IFERROR(INDEX(Аналитика!`$S`$2:`$S`$14,MATCH(LARGE($W,$k),$W,0)),`"—`")"
  $fD = "IFERROR(INDEX(Аналитика!`$V`$2:`$V`$14,MATCH(LARGE($W,$k),$W,0)),`"`")"
  $s5 = Replace-Cell $s5 "B$rowN" ('<c r="B' + $rowN + '" s="' + $sB + '"><f>' + $fB + '</f></c>')
  $s5 = Replace-Cell $s5 "D$rowN" ('<c r="D' + $rowN + '" s="' + $sD + '"><f>' + $fD + '</f></c>')
}
# вывод по способам — ссылаться на 1-е место, а не на 2-е
$mx = 'MAX(Аналитика!$V$2:$V$14)'
$f39 = "IF($mx&gt;70,`"Ваши способы совладания в целом эффективны. Лучший способ: `"&amp;B33&amp;`" (`"&amp;TEXT(D33,`"0`")&amp;`"%).`n" +
       "Рекомендуется использовать его чаще и добавлять новые практики.`",IF($mx&gt;50,`"Средняя эффективность способов совладания. Лучший способ: `"&amp;B33&amp;`" (`"&amp;TEXT(D33,`"0`")&amp;`"%).`n" +
       "Попробуйте добавить новые техники: медитация, дневник благодарности, физическая активность.`",`"Низкая эффективность способов совладания. Ваш лучший способ: `"&amp;B33&amp;`" (`"&amp;TEXT(D33,`"0`")&amp;`"%).`n" +
       "Рекомендуется проконсультироваться с психологом и освоить новые техники регуляции эмоций.`"))"
$s5 = Replace-Cell $s5 'A39' ('<c r="A39" s="54"><f>' + $f39 + '</f></c>')
# рекомендация по эмоции — не падать в #Н/Д
$s5 = Replace-Cell $s5 'B47' '<c r="B47" s="35"><f>IFERROR(VLOOKUP(B46,Справочники!$A$2:$G$50,7,FALSE),"—")</f></c>'
# заготовки текста A27-A29 и выбор A30 — на индекс тонуса, а не на строку соотношения
$cnt = ([regex]::Matches($s5, 'Аналитика!B8')).Count
if ($cnt -ne 5) { throw "ожидалось 5 ссылок Аналитика!B8 (A27,A28,A29 по одной; A30 две), найдено $cnt" }
$s5 = $s5.Replace('Аналитика!B8', 'Аналитика!B7')
Write-Part 'xl\worksheets\sheet5.xml' $s5
Note "Этап 3: сдвиг ссылок исправлен (B3,B5,B6,B7,B12,A27-A30), даты через TEXT, ТОП-3 эмоций и ТОП-5 способов без повторов, A39 -> 1-е место, B47 в IFERROR"

# =============================================================================
# ЭТАП 6 — «Дашборд» (sheet7): заголовок и возврат на «Главную»
# =============================================================================
$s7 = Read-Part 'xl\worksheets\sheet7.xml'
$rows = '<sheetData>' +
        '<row r="1" spans="1:4" ht="21" customHeight="1"><c r="A1" s="50" t="inlineStr"><is><t>📈 ДАШБОРД</t></is></c></row>' +
        '<row r="2" spans="1:4"><c r="A2" s="28" t="inlineStr"><is><t>🏠 На главную</t></is></c></row>' +
        '</sheetData>'
$s7 = $s7.Replace('<sheetData/>', $rows)
$s7 = $s7.Replace('<dimension ref="A1"/>', '<dimension ref="A1:A2"/>')
$hl = '<hyperlinks><hyperlink ref="A2" location="Главная!A1" display="🏠 На главную"/></hyperlinks>'
$s7 = $s7.Replace('<pageMargins', $hl + '<pageMargins')
Write-Part 'xl\worksheets\sheet7.xml' $s7
Note "Этап 6: лист и 5 диаграмм сохранены, добавлен заголовок и ссылка возврата на «Главную»"

# =============================================================================
# Пересчёт: убрать calcChain, включить fullCalcOnLoad
# =============================================================================
Remove-Item (Join-Path $work 'xl\calcChain.xml') -Force
$ct = Read-Part '[Content_Types].xml'
$ct = [regex]::Replace($ct, '<Override PartName="/xl/calcChain\.xml"[^>]*/>', '')
Write-Part '[Content_Types].xml' $ct
$wr = Read-Part 'xl\_rels\workbook.xml.rels'
$wr = [regex]::Replace($wr, '<Relationship Id="[^"]*" Type="[^"]*/calcChain" Target="calcChain\.xml"\s*/>', '')
Write-Part 'xl\_rels\workbook.xml.rels' $wr
$wb = Read-Part 'xl\workbook.xml'
$wb = $wb.Replace('<calcPr calcId="191029"/>', '<calcPr calcId="191029" fullCalcOnLoad="1"/>')
Write-Part 'xl\workbook.xml' $wb
Note "Пересчёт: calcChain.xml удалён, включён fullCalcOnLoad"

# =============================================================================
# Сборка пакета
# =============================================================================
$out = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName() + '.xlsx')
[System.IO.Compression.ZipFile]::CreateFromDirectory($work, $out, [System.IO.Compression.CompressionLevel]::Optimal, $false)
Move-Item -LiteralPath $out -Destination $Xlsx -Force
Remove-Item $work -Recurse -Force
Note ("Готово: " + $Xlsx + " (" + (Get-Item $Xlsx).Length + " байт)")
