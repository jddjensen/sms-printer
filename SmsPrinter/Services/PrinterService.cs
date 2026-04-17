using System.Runtime.InteropServices;
using System.Text;

namespace SmsPrinter.Services;

public class PrinterService
{
    public bool PrintingEnabled { get; set; } = true;

    private const string PrinterName = "POS-80";

    public void Print(string from, string body)
    {
        var timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
        var text = $"\nNEW MESSAGE\n{new string('-', 32)}\nFrom: {from}\nTime: {timestamp}\n{new string('-', 32)}\n\n{body}\n\n\n\n\n\n";
        var textBytes = Encoding.UTF8.GetBytes(text);
        byte[] cut = [0x1d, 0x56, 0x41, 0x05];
        var raw = new byte[textBytes.Length + cut.Length];
        textBytes.CopyTo(raw, 0);
        cut.CopyTo(raw, textBytes.Length);

        if (!NativeMethods.OpenPrinter(PrinterName, out var hPrinter, IntPtr.Zero))
            throw new InvalidOperationException($"Cannot open printer '{PrinterName}'");

        try
        {
            var doc = new NativeMethods.DOCINFO
            {
                pDocName = "SMS",
                pOutputFile = null,
                pDatatype = "RAW"
            };
            NativeMethods.StartDocPrinter(hPrinter, 1, ref doc);
            NativeMethods.StartPagePrinter(hPrinter);
            NativeMethods.WritePrinter(hPrinter, raw, raw.Length, out _);
            NativeMethods.EndPagePrinter(hPrinter);
            NativeMethods.EndDocPrinter(hPrinter);
        }
        finally
        {
            NativeMethods.ClosePrinter(hPrinter);
        }
    }
}

internal static class NativeMethods
{
    [DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern bool OpenPrinter(string pPrinterName, out IntPtr phPrinter, IntPtr pDefault);

    [DllImport("winspool.drv", SetLastError = true)]
    internal static extern bool ClosePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern int StartDocPrinter(IntPtr hPrinter, int Level, [In] ref DOCINFO pDocInfo);

    [DllImport("winspool.drv", SetLastError = true)]
    internal static extern bool EndDocPrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", SetLastError = true)]
    internal static extern bool StartPagePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", SetLastError = true)]
    internal static extern bool EndPagePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", SetLastError = true)]
    internal static extern bool WritePrinter(IntPtr hPrinter, byte[] pBuf, int cbBuf, out int pcWritten);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    internal struct DOCINFO
    {
        [MarshalAs(UnmanagedType.LPWStr)] public string pDocName;
        [MarshalAs(UnmanagedType.LPWStr)] public string? pOutputFile;
        [MarshalAs(UnmanagedType.LPWStr)] public string pDatatype;
    }
}
