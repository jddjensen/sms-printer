using SmsPrinter.Hubs;
using SmsPrinter.Models;
using SmsPrinter.Services;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSignalR();
builder.Services.AddSingleton<PrinterService>();

var app = builder.Build();
app.UseDefaultFiles();
app.UseStaticFiles();
app.MapHub<PrinterHub>("/printerHub");

app.MapPost("/sms", async (
    HttpRequest request,
    PrinterService printer,
    IHubContext<PrinterHub, IPrinterClient> hub) =>
{
    var form = await request.ReadFormAsync();
    var from = form["From"].FirstOrDefault() ?? "Unknown";
    var body = form["Body"].FirstOrDefault() ?? "";
    var time = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");

    string status;
    if (!printer.PrintingEnabled)
    {
        status = "skipped";
        Console.WriteLine("Printing paused — message skipped.");
    }
    else
    {
        try
        {
            printer.Print(from, body);
            Console.WriteLine("Printed successfully.");
            status = "printed";
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Print error: {ex.Message}");
            status = "error";
        }
    }

    await hub.Clients.All.NewMessage(new SmsMessage(from, body, time, status));
    return Results.Content(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>",
        "text/xml");
});

app.MapPost("/shutdown", () =>
{
    Task.Delay(500).ContinueWith(_ => Environment.Exit(0));
    return Results.Ok(new { ok = true });
});

Console.WriteLine("SMS Printer running on http://localhost:5000");
app.Run("http://0.0.0.0:5000");
