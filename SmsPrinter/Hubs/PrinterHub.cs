using Microsoft.AspNetCore.SignalR;
using SmsPrinter.Models;
using SmsPrinter.Services;

namespace SmsPrinter.Hubs;

public interface IPrinterClient
{
    Task NewMessage(SmsMessage message);
    Task PrintingState(PrintingStateDto state);
}

public class PrinterHub : Hub<IPrinterClient>
{
    private readonly PrinterService _printer;

    public PrinterHub(PrinterService printer) => _printer = printer;

    public override async Task OnConnectedAsync()
    {
        await Clients.Caller.PrintingState(new PrintingStateDto(_printer.PrintingEnabled));
        await base.OnConnectedAsync();
    }

    public async Task SetPrinting(bool enabled)
    {
        _printer.PrintingEnabled = enabled;
        await Clients.All.PrintingState(new PrintingStateDto(enabled));
    }
}
